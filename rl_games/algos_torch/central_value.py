import torch
from torch import nn
import numpy as np
from rl_games.algos_torch import torch_ext
from rl_games.algos_torch.running_mean_std import RunningMeanStd




class CentralValueTrain(nn.Module):
    def __init__(self, state_shape, model, config, writter, _preproc_obs):
        nn.Module.__init__(self)
        state_config = {
            'input_shape' : state_shape,
        }
        
        self.model = model.build('cvalue', **cv_config).cuda()
        self.config = config
        self.lr = config['lr']
        self.mini_epoch = self.config['mini_epochs']
        self.mini_batch = self.config['minibatch_size']

        self.writter = writter
        self.optimizer = torch.optim.Adam(self.model.parameters(), float(self.lr))
        self._preproc_obs = _preproc_obs
        self.frame = 0

    def train(self, obs):
        self.model.train()

        states = batch_dict['a_states']

        num_minibatches = np.shape(obs)[0] // mini_batch
        self.frame = self.frame + 1
        for _ in range(self.mini_epoch):
            # returning loss from last epoch
            avg_loss = 0
            for i in range(self.num_minibatches):
                obs_batch = obs[i * mini_batch: (i + 1) * mini_batch]
                obs_batch = self._preproc_obs(obs_batch)
                loss = self.model(obs_batch).mean()
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                avg_loss += loss.item()

        self.writter.add_scalar('cval/train_loss', avg_loss, self.frame)
        return avg_loss / num_minibatches