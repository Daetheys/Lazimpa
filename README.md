# LazImpa

This repository gathers the code used for all the experiments of the following paper:

- *“LazImpa”: Lazy and Impatient neural agents learn to communicate efficiently* (under review)

The code is an extension of EGG toolkit (https://github.com/facebookresearch/EGG) presented in *EGG: a toolkit for research on Emergence of lanGuage in Games*, Eugene Kharitonov, Rahma Chaabouni, Diane Bouchacourt, Marco Baroni. EMNLP 2019.

## Presentation

#### The game

`LazImpa` repository implements a Speaker/Listener game where agents have to cooperatly communicate in order to win the game. The Speaker receives an input (one-hot vector) it has to communicate to the Listener. To do so, it sends a message $m$ to the Listener. The Listener consumes the message and output a candidate. The agents are then succesful if the Listener correctly reconstructes the ground-truth input.

#### The aim of the paper

The aim of the paper 

## Run the code

We show here an example of experiment that can be run on Google Colab (smaller input space than in the paper). We also provide a notebook (**LINK**) that can merely be run in Colab to quickly reproduce our results on a smaller input space. The command line that are run for our paper results are reported below in the section [Reproductibility](http://github.com/MathieuRita/LE_test#Reproductibility).

### Command lines

1. First clone the repository:
```
git clone https://github.com/MathieuRita/LE_test.git
mv "./LE_test/egg" "./egg"
```

2. Create a directory in which all the useful data will be saved (you have to respect the following hierarchy):

```
mkdir dir_save
mkdir dir_save/sender
mkdir dir_save/receiver
mkdir dir_save/messages
mkdir dir_save/accuracy
```


3. Train agents:

```
python -m egg.zoo.channel.train   --dir_save=dir_save \
                                  --vocab_size=40 \
                                  --max_len=30 \
                                  --impatient=True \
                                  --reg=True \
                                  --n_features=100 \
                                  --print_message=False \
                                  --random_seed=7 \
                                  --probs="powerlaw" \
                                  --n_epoch=201 \
                                  --batch_size=512 \
                                  --length_cost=0. \
                                  --sender_cell="lstm" \
                                  --receiver_cell="lstm" \
                                  --sender_hidden=250 \
                                  --receiver_hidden=600 \
                                  --receiver_embedding=100 \
                                  --sender_embedding=10 \
                                  --batches_per_epoch=100 \
                                  --lr=0.001 \
                                  --sender_entropy_coeff=2. \
                                  --sender_num_layers=1 \
                                  --receiver_num_layers=1 \
                                  --early_stopping_thr=0.99
```

4. Test agents:

**TO DO**

### H-parameters description

H-params can be divided in 3 classes: experiment H-params, architecture H-params, optimization H-params, backup H-params. Here is a description of the main H-parameters:

1. Experiment H-params:
- `vocab_size`: size of vocabulary in the communication channel (default=40)
- `max_len`: maximum length of the message in the communication channel (default=30)
- `n_features`: dimensionality of the concept space (number of inputs)
- `probs`: frequency distribution of the inputs (default=`powerlaw`)

2. Architecture H-params:
- `impatient`: if set to `True`, the Receiver is made Impatient
- `reg`: if set to `True`, the Sender is made Lazy
- `sender_cell`: type of Sender recurrent cell (in the whole paper: `lstm`)
- `sender_hidden`: Size of the hidden layer of Sender
- `sender_embedding`: Dimensionality of the embedding hidden layer for Sender
- `sender_num_layers`: Number hidden layers of Sender
- `receiver_cell`: type of Sender recurrent cell (in the whole paper: `lstm`)
- `receiver_hidden`: Size of the hidden layer of Receiver
- `receiver_embedding`: Dimensionality of the embedding hidden layer for Receiver
- `receiver_num_layers`: Number hidden layers of Receiver

3. Optimization H-params:
- `n_epochs`: number of training episodes
- `batches_per_epoch`: number of batches per training episode
- `batch_size`: size of a batch
- `lr`: learning rate
- `sender_entropy_coeff`: The entropy regularisation coefficient for Sender (trade-off between exploration/exploitation)
- `length_cost`: penalty applied on message length (if `reg` is set to `True`, this penalty is schedulded as done in the paper)

## Paper results

## Reproductibility

To reproduce the results obtained in the paper for LazImpa, just run the following command line (you can choose any seed. Please note that `n_epochs` may be set to a larger value for certain seeds):

```
python -m egg.zoo.channel.train   --dir_save=dir_save --vocab_size=40 --max_len=30 --impatient=True --reg=True --n_features=1000 --print_message=False --random_seed=1 --probs="powerlaw" --n_epoch=2501 --batch_size=512 --length_cost=0. --sender_cell="lstm" --receiver_cell="lstm" --sender_hidden=250 --receiver_hidden=600 --receiver_embedding=100 --sender_embedding=10 --batches_per_epoch=100 --lr=0.001 --sender_entropy_coeff=2. --sender_num_layers=1 --receiver_num_layers=1 --early_stopping_thr=0.99
```

If you also want to reproduce the baselines shown in the paper, you just have to play with the Hparams `impatient` and `reg` (the other Hparams can be unchainged):

- *LazImpa* : `impatient=True`, `reg=True`
- *Standard agents*: `impatient=False`, `reg=False`
- *Standard Listener + Lazy Speaker*: `impatient=False`, `reg=True`
- *Impatient Listener + Standard Speaker*: `impatient=True`, `reg=True`

To reproduce the natural language curves, please find the right corpus here: [Natural languages corpus](http://corpus.leeds.ac.uk/serge/).

## How to cite ?

The paper is currently under review.
