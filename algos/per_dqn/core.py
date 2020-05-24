"""Core functions for PER, mainly the PER version of the RL Dataset"""
from typing import Tuple
from torch.utils.data import IterableDataset
from algos.common.memory import PERBuffer


class PrioRLDataset(IterableDataset):
    """
    Iterable Dataset containing the ExperienceBuffer
    which will be updated with new experiences during training

    Args:
        buffer: replay buffer
        sample_size: number of experiences to sample at a time
    """

    def __init__(self, buffer: PERBuffer, sample_size: int = 1) -> None:
        self.buffer = buffer
        self.sample_size = sample_size

    def __iter__(self) -> Tuple:
        samples, indices, weights = self.buffer.sample(self.sample_size)

        # for idx, sample in enumerate(samples):
        #     yield sample, indices[idx], weights[idx]

        states, actions, rewards, dones, new_states = samples
        for idx, _ in enumerate(dones):
            yield (states[idx], actions[idx], rewards[idx], dones[idx], new_states[idx]), indices[idx], weights[idx]



    def __getitem__(self, item):
        """Not used"""
        return None