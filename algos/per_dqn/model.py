"""
Deep Reinforcement Learning: Deep Q-network (DQN)
This example is based on https://github.com/PacktPublishing/Deep-Reinforcement-Learning-Hands-On-
Second-Edition/blob/master/Chapter06/02_dqn_pong.py
The template illustrates using Lightning for Reinforcement Learning. The example builds a basic DQN using the
classic CartPole environment.
To run the template just run:
python reinforce_learn_Qnet.py
After ~1500 steps, you will see the total_reward hitting the max score of 200. Open up TensorBoard to
see the metrics:
tensorboard --logdir default
"""

from collections import OrderedDict
from typing import Tuple, List
import torch
from torch.utils.data import DataLoader

from algos.common.memory import PERBuffer
from algos.dqn.core import Agent
from algos.dqn.model import DQNLightning
from algos.per_dqn.core import PrioRLDataset


class PERDQNLightning(DQNLightning):
    """ PER DQN Model """

    def __init__(self, hparams):
        super().__init__(hparams)

        self.buffer = PERBuffer(self.hparams.replay_size)

        self.agent = Agent(self.env, self.buffer)
        self.populate(self.hparams.warm_start_steps)

    def training_step(self, batch, _) -> OrderedDict:
        """
        Carries out a single step through the environment to update the replay buffer.
        Then calculates loss based on the minibatch recieved

        Args:
            batch: current mini batch of replay data
            _: batch number, not used

        Returns:
            Training loss and log metrics
        """
        samples, indices, weights = batch

        indices = indices.cpu().numpy()

        device = self.get_device(samples)
        epsilon = max(self.hparams.eps_end, self.hparams.eps_start -
                      (self.global_step + 1) / self.hparams.eps_last_frame)

        # step through environment with agent
        reward, done = self.agent.play_step(self.net, epsilon, device)
        self.episode_reward += reward
        self.episode_steps += 1

        # calculates training loss
        loss, batch_weights = self.loss(samples, weights)

        # update priorities in buffer
        self.buffer.update_priorities(indices, batch_weights)
        # self.buffer.update_beta(self.global_step)

        if self.trainer.use_dp or self.trainer.use_ddp2:
            loss = loss.unsqueeze(0)

        if done:
            self.total_reward = self.episode_reward
            self.episode_count += 1
            self.episode_reward = 0
            self.total_episode_steps = self.episode_steps
            self.episode_steps = 0

        # Soft update of target network
        if self.global_step % self.hparams.sync_rate == 0:
            self.target_net.load_state_dict(self.net.state_dict())

        log = {'total_reward': torch.tensor(self.total_reward).to(device),
               'train_loss': loss,
               'episode_steps': torch.tensor(self.total_episode_steps)
               }
        status = {'steps': torch.tensor(self.global_step).to(device),
                  'total_reward': torch.tensor(self.total_reward).to(device),
                  'episodes': self.episode_count,
                  'episode_steps': self.episode_steps,
                  'epsilon': epsilon
                  }

        return OrderedDict({'loss': loss, 'log': log, 'progress_bar': status})

    def loss(self, batch: Tuple[torch.Tensor, torch.Tensor], batch_weights: List) -> Tuple[torch.Tensor, List]:
        """
        Calculates the mse loss with the priority weights of the batch from the PER buffer

        Args:
            batch: current mini batch of replay data
            batch_weights: how each of these samples are weighted in terms of priority

        Returns:
            loss
        """
        states, actions, rewards, dones, next_states = batch

        batch_weights = torch.tensor(batch_weights)

        actions_v = actions.unsqueeze(-1)
        state_action_vals = self.net(states).gather(1, actions_v)
        state_action_vals = state_action_vals.squeeze(-1)
        with torch.no_grad():
            next_s_vals = self.target_net(next_states).max(1)[0]
            next_s_vals[dones] = 0.0
            exp_sa_vals = next_s_vals.detach() * self.hparams.gamma + rewards
        loss = (state_action_vals - exp_sa_vals) ** 2
        losses_v = batch_weights * loss
        return losses_v.mean(), (losses_v + 1e-5).data.cpu().numpy()

    def _dataloader(self) -> DataLoader:
        """Initialize the Replay Buffer dataset used for retrieving experiences"""
        dataset = PrioRLDataset(self.buffer, self.hparams.batch_size)
        dataloader = DataLoader(dataset=dataset,
                                batch_size=self.hparams.batch_size,
                                )
        return dataloader