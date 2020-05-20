# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import argparse
import numpy as np
import itertools
import torch.utils.data
import torch.nn.functional as F
import egg.core as core
from egg.core import EarlyStopperAccuracy
from egg.zoo.channel.features import OneHotLoader, UniformLoader
from egg.zoo.channel.archs import Sender, Receiver
from egg.core.reinforce_wrappers import RnnReceiverImpatient, RnnReceiverImpatientCompositionality
from egg.core.reinforce_wrappers import SenderImpatientReceiverRnnReinforce, CompositionalitySenderImpatientReceiverRnnReinforce
from egg.core.util import dump_sender_receiver_impatient, dump_sender_receiver_impatient_compositionality

from egg.core.trainers import CompoTrainer


def get_params(params):
    parser = argparse.ArgumentParser()
    parser.add_argument('--n_features', type=int, default=10,
                        help='Dimensionality of the "concept" space (default: 10)')
    parser.add_argument('--batches_per_epoch', type=int, default=1000,
                        help='Number of batches per epoch (default: 1000)')
    parser.add_argument('--dim_dataset', type=int, default=10240,
                        help='Dim of constructing the data (default: 10240)')
    parser.add_argument('--force_eos', type=int, default=0,
                        help='Force EOS at the end of the messages (default: 0)')

    parser.add_argument('--sender_hidden', type=int, default=10,
                        help='Size of the hidden layer of Sender (default: 10)')
    parser.add_argument('--receiver_hidden', type=int, default=10,
                        help='Size of the hidden layer of Receiver (default: 10)')
    parser.add_argument('--receiver_num_layers', type=int, default=1,
                        help='Number hidden layers of receiver. Only in reinforce (default: 1)')
    parser.add_argument('--sender_num_layers', type=int, default=1,
                        help='Number hidden layers of receiver. Only in reinforce (default: 1)')
    parser.add_argument('--receiver_num_heads', type=int, default=8,
                        help='Number of attention heads for Transformer Receiver (default: 8)')
    parser.add_argument('--sender_num_heads', type=int, default=8,
                        help='Number of self-attention heads for Transformer Sender (default: 8)')
    parser.add_argument('--sender_embedding', type=int, default=10,
                        help='Dimensionality of the embedding hidden layer for Sender (default: 10)')
    parser.add_argument('--receiver_embedding', type=int, default=10,
                        help='Dimensionality of the embedding hidden layer for Receiver (default: 10)')

    parser.add_argument('--causal_sender', default=False, action='store_true')
    parser.add_argument('--causal_receiver', default=False, action='store_true')

    parser.add_argument('--sender_generate_style', type=str, default='in-place', choices=['standard', 'in-place'],
                        help='How the next symbol is generated within the TransformerDecoder (default: in-place)')

    parser.add_argument('--sender_cell', type=str, default='rnn',
                        help='Type of the cell used for Sender {rnn, gru, lstm, transformer} (default: rnn)')
    parser.add_argument('--receiver_cell', type=str, default='rnn',
                        help='Type of the model used for Receiver {rnn, gru, lstm, transformer} (default: rnn)')

    parser.add_argument('--sender_entropy_coeff', type=float, default=1e-1,
                        help='The entropy regularisation coefficient for Sender (default: 1e-1)')
    parser.add_argument('--receiver_entropy_coeff', type=float, default=1e-1,
                        help='The entropy regularisation coefficient for Receiver (default: 1e-1)')

    parser.add_argument('--probs', type=str, default='uniform',
                        help="Prior distribution over the concepts (default: uniform)")
    parser.add_argument('--length_cost', type=float, default=0.0,
                        help="Penalty for the message length, each symbol would before <EOS> would be "
                             "penalized by this cost (default: 0.0)")
    parser.add_argument('--name', type=str, default='model',
                        help="Name for your checkpoint (default: model)")
    parser.add_argument('--early_stopping_thr', type=float, default=0.9999,
                        help="Early stopping threshold on accuracy (default: 0.9999)")

    # AJOUT
    parser.add_argument('--dir_save', type=str, default="expe_1",
                        help="Directory in which we will save the information")
    parser.add_argument('--unigram_pen', type=float, default=0.0,
                        help="Add a penalty for redundancy")
    parser.add_argument('--impatient', type=bool, default=False,
                        help="Impatient listener")
    parser.add_argument('--print_message', type=bool, default=False,
                        help='Print message ?')
    parser.add_argument('--reg', type=bool, default=False,
                        help='Add regularization ?')

    # Compositionality
    parser.add_argument('--n_attributes', type=int, default=3,
                        help='Number of attributes (default: 2)')
    parser.add_argument('--n_values', type=int, default=3,
                        help='Number of values by attribute')

    args = core.init(parser, params)

    return args


def loss(sender_input, _message, _receiver_input, receiver_output, _labels):
    acc = (receiver_output.argmax(dim=1) == sender_input.argmax(dim=1)).detach().float()
    loss = F.cross_entropy(receiver_output, sender_input.argmax(dim=1), reduction="none")
    return loss, {'acc': acc}

def loss_impatient(sender_input, _message, message_length, _receiver_input, receiver_output, _labels):

    to_onehot=torch.eye(_message.size(1)).to("cuda")
    to_onehot=torch.cat((to_onehot,torch.zeros((1,_message.size(1))).to("cuda")),0)
    len_mask=[]
    for i in range(message_length.size(0)):
      len_mask.append(to_onehot[message_length[i]])
    len_mask=torch.stack(len_mask,dim=0)

    coef=(1/message_length.to(float)).repeat(_message.size(1),1).transpose(1,0)
    coef2=coef*torch.arange(_message.size(1),0,-1).repeat(_message.size(0),1).to("cuda")

    len_mask=torch.cumsum(len_mask,dim=1)
    len_mask=torch.ones(len_mask.size()).to("cuda").add_(-len_mask)

    len_mask.mul_((coef2))
    len_mask.mul_((1/len_mask.sum(1)).repeat((_message.size(1),1)).transpose(1,0))

    crible_acc=torch.zeros(size=_message.size()).to("cuda")
    crible_loss=torch.zeros(size=_message.size()).to("cuda")

    for i in range(receiver_output.size(1)):
      crible_acc[:,i].add_((receiver_output[:,i,:].argmax(dim=1) == sender_input.argmax(dim=1)).detach().float())
      crible_loss[:,i].add_(F.cross_entropy(receiver_output[:,i,:], sender_input.argmax(dim=1), reduction="none"))

    acc=crible_acc*len_mask
    loss=crible_loss*len_mask

    acc = acc.sum(1)
    loss= loss.sum(1)

    return loss, {'acc': acc}, crible_acc

def loss_impatient_compositionality(sender_input, _message, message_length, _receiver_input, receiver_output, _labels):

    to_onehot=torch.eye(_message.size(1)).to("cuda")
    to_onehot=torch.cat((to_onehot,torch.zeros((1,_message.size(1))).to("cuda")),0)
    len_mask=[]
    for i in range(message_length.size(0)):
      len_mask.append(to_onehot[message_length[i]])
    len_mask=torch.stack(len_mask,dim=0)

    coef=(1/message_length.to(float)).repeat(_message.size(1),1).transpose(1,0)
    coef2=coef*torch.arange(_message.size(1),0,-1).repeat(_message.size(0),1).to("cuda")

    len_mask=torch.cumsum(len_mask,dim=1)
    len_mask=torch.ones(len_mask.size()).to("cuda").add_(-len_mask)

    len_mask.mul_((coef2))
    len_mask.mul_((1/len_mask.sum(1)).repeat((_message.size(1),1)).transpose(1,0))

    crible_acc=torch.zeros(size=_message.size()).to("cuda")
    crible_loss=torch.zeros(size=_message.size()).to("cuda")

    for i in range(receiver_output.size(1)):
      crible_acc[:,i].add_((receiver_output[:,i,:].argmax(dim=1) == sender_input.argmax(dim=1)).detach().float())
      crible_loss[:,i].add_(F.cross_entropy(receiver_output[:,i,:], sender_input.argmax(dim=1), reduction="none"))

    acc=crible_acc*len_mask
    loss=crible_loss*len_mask

    acc = acc.sum(1)
    loss= loss.sum(1)

    return loss, {'acc': acc}, crible_acc

def dump(game, n_features, device, gs_mode, epoch):
    # tiny "dataset"
    dataset = [[torch.eye(n_features).to(device), None]]

    sender_inputs, messages, receiver_inputs, receiver_outputs, _ = \
        core.dump_sender_receiver(game, dataset, gs=gs_mode, device=device, variable_length=True)

    unif_acc = 0.
    powerlaw_acc = 0.
    powerlaw_probs = 1 / np.arange(1, n_features+1, dtype=np.float32)
    powerlaw_probs /= powerlaw_probs.sum()

    acc_vec=np.zeros(n_features)

    for sender_input, message, receiver_output in zip(sender_inputs, messages, receiver_outputs):
        input_symbol = sender_input.argmax()
        output_symbol = receiver_output.argmax()
        acc = (input_symbol == output_symbol).float().item()

        acc_vec[int(input_symbol)]=acc

        unif_acc += acc
        powerlaw_acc += powerlaw_probs[input_symbol] * acc
        if epoch%25==0 or epoch>300:
            print(f'input: {input_symbol.item()} -> message: {",".join([str(x.item()) for x in message])} -> output: {output_symbol.item()}', flush=True)

    unif_acc /= n_features

    #print(f'Mean accuracy wrt uniform distribution is {unif_acc}')
    #print(f'Mean accuracy wrt powerlaw distribution is {powerlaw_acc}')
    print(json.dumps({'powerlaw': powerlaw_acc, 'unif': unif_acc}))

    return acc_vec, messages

def dump_impatient(game, n_features, device, gs_mode,epoch):
    # tiny "dataset"
    dataset = [[torch.eye(n_features).to(device), None]]

    sender_inputs, messages, receiver_inputs, receiver_outputs, _ = \
        dump_sender_receiver_impatient(game, dataset, gs=gs_mode, device=device, variable_length=True)

    unif_acc = 0.
    powerlaw_acc = 0.
    powerlaw_probs = 1 / np.arange(1, n_features+1, dtype=np.float32)
    powerlaw_probs /= powerlaw_probs.sum()

    acc_vec=np.zeros(n_features)

    for sender_input, message, receiver_output in zip(sender_inputs, messages, receiver_outputs):
        input_symbol = sender_input.argmax()
        output_symbol = receiver_output.argmax()
        acc = (input_symbol == output_symbol).float().item()

        acc_vec[int(input_symbol)]=acc

        unif_acc += acc
        powerlaw_acc += powerlaw_probs[input_symbol] * acc
        if epoch%25==0 or epoch>300:
            print(f'input: {input_symbol.item()} -> message: {",".join([str(x.item()) for x in message])} -> output: {output_symbol.item()}', flush=True)

    unif_acc /= n_features

    #print(f'Mean accuracy wrt uniform distribution is {unif_acc}')
    #print(f'Mean accuracy wrt powerlaw distribution is {powerlaw_acc}')
    print(json.dumps({'powerlaw': powerlaw_acc, 'unif': unif_acc}))

    return acc_vec, messages

def dump_impatient_compositionality(game, n_attributes, n_values, device, gs_mode,epoch):
    # tiny "dataset"
    one_hots = torch.eye(n_values)

    val=np.arange(n_values)
    combination=list(itertools.product(val,repeat=n_attributes))

    dataset=[]

    for i in range(len(comb)):
      new_input=torch.zeros(0)
      for j in comb[i]:
        new_input=torch.cat((new_input,one_hots[j]))
      dataset.append(new_input)

    dataset=torch.stack(dataset)

    dataset=[[dataset,None]]

    sender_inputs, messages, receiver_inputs, receiver_outputs, _ = \
        dump_sender_receiver_impatient_compositionality(game, dataset, gs=gs_mode, device=device, variable_length=True)

    unif_acc = 0.

    acc_vec=np.zeros(n_features)

    print(sender_inputs)
    print(receiver_outputs)

    for sender_input, message, receiver_output in zip(sender_inputs, messages, receiver_outputs):
        input_symbol = sender_input.argmax()
        output_symbol = receiver_output.argmax()
        acc = (input_symbol == output_symbol).float().item()

        acc_vec[int(input_symbol)]=acc

        unif_acc += acc
        powerlaw_acc += powerlaw_probs[input_symbol] * acc

        print(f'input: {input_symbol.item()} -> message: {",".join([str(x.item()) for x in message])} -> output: {output_symbol.item()}', flush=True)

    unif_acc /= n_features

    #print(f'Mean accuracy wrt uniform distribution is {unif_acc}')
    #print(f'Mean accuracy wrt powerlaw distribution is {powerlaw_acc}')
    print(json.dumps({'unif': unif_acc}))

    return acc_vec, messages

def main(params):
    print(torch.cuda.is_available())
    opts = get_params(params)
    print(opts, flush=True)
    device = opts.device

    force_eos = opts.force_eos == 1

    # Distribution of the inputs
    probs = np.ones(opts.n_values)
    probs /= probs.sum()


    train_loader = OneHotLoader(n_features=opts.n_values, batch_size=opts.batch_size*opts.n_attributes,
                                batches_per_epoch=opts.batches_per_epoch, probs=probs)

    # single batches with 1s on the diag
    test_loader = UniformLoader(opts.n_values)

    ### SENDER ###

    sender = Sender(n_features=opts.n_attributes*opts.n_values, n_hidden=opts.sender_hidden)

    sender = core.RnnSenderReinforce(sender,opts.vocab_size, opts.sender_embedding, opts.sender_hidden,
                                   cell=opts.sender_cell, max_len=opts.max_len, num_layers=opts.sender_num_layers,
                                   force_eos=force_eos)


    ### RECEIVER ###

    receiver = Receiver(n_features=opts.n_values, n_hidden=opts.receiver_hidden)

    if not opts.impatient:
        receiver = Receiver(n_features=opts.n_features, n_hidden=opts.receiver_hidden)
        receiver = core.RnnReceiverDeterministic(receiver, opts.vocab_size, opts.receiver_embedding,
                                                 opts.receiver_hidden, cell=opts.receiver_cell,
                                                 num_layers=opts.receiver_num_layers)
    else:
        receiver = Receiver(n_features=opts.receiver_hidden, n_hidden=opts.vocab_size)
        # If impatient 1
        receiver = RnnReceiverImpatientCompositionality(receiver, opts.vocab_size, opts.receiver_embedding,
                                            opts.receiver_hidden, cell=opts.receiver_cell,
                                            num_layers=opts.receiver_num_layers, max_len=opts.max_len, n_attributes=opts.n_attributes, n_values=opts.n_values)


    if not opts.impatient:
        game = core.SenderReceiverRnnReinforce(sender, receiver, loss, sender_entropy_coeff=opts.sender_entropy_coeff,
                                           receiver_entropy_coeff=opts.receiver_entropy_coeff,
                                           length_cost=opts.length_cost,unigram_penalty=opts.unigram_pen,reg=opts.reg)
    else:
        game = CompositionalitySenderImpatientReceiverRnnReinforce(sender, receiver, loss_impatient_compositionality, sender_entropy_coeff=opts.sender_entropy_coeff,
                                           n_attributes=opts.n_attributes,n_values=opts.n_values,receiver_entropy_coeff=opts.receiver_entropy_coeff,
                                           length_cost=opts.length_cost,unigram_penalty=opts.unigram_pen,reg=opts.reg)

    optimizer = core.build_optimizer(game.parameters())

    trainer = core.CompoTrainer(n_attributes=opts.n_attributes,n_values=opts.n_values,game=game, optimizer=optimizer, train_data=train_loader,
                           validation_data=test_loader, callbacks=[EarlyStopperAccuracy(opts.early_stopping_thr)])


    for epoch in range(int(opts.n_epochs)):

        print("Epoch: "+str(epoch))

        if epoch%100==0:
          trainer.optimizer.defaults["lr"]/=2

        trainer.train(n_epochs=1)
        if opts.checkpoint_dir:
            trainer.save_checkpoint(name=f'{opts.name}_vocab{opts.vocab_size}_rs{opts.random_seed}_lr{opts.lr}_shid{opts.sender_hidden}_rhid{opts.receiver_hidden}_sentr{opts.sender_entropy_coeff}_reg{opts.length_cost}_max_len{opts.max_len}')

        if not opts.impatient:
            acc_vec,messages=dump(trainer.game, opts.n_features, device, False,epoch)
        else:
            acc_vec,messages=dump_impatient_compositionality(trainer.game, opts.n_attributes, opts.n_values, device, False,epoch)

        # ADDITION TO SAVE MESSAGES
        all_messages=[]
        for x in messages:
            x = x.cpu().numpy()
            all_messages.append(x)
        all_messages = np.asarray(all_messages)

        if epoch%50==0:
            torch.save(sender.state_dict(), opts.dir_save+"/sender/sender_weights"+str(epoch)+".pth")
            torch.save(receiver.state_dict(), opts.dir_save+"/receiver/receiver_weights"+str(epoch)+".pth")

        np.save(opts.dir_save+'/messages/messages_'+str((epoch))+'.npy', all_messages)
        np.save(opts.dir_save+'/accuracy/accuracy_'+str((epoch))+'.npy', acc_vec)
        print(acc_vec)

    core.close()


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])