"""
This package contains `DeepCopyableGame` and its implementations. See implementations for details.
"""

import numpy
import typing

import abc
from copy import deepcopy

import gymnasium as gym

from mcts_general.common.wrapper import DeepCopyableWrapper, DiscreteActionWrapper


class DeepCopyableGame(metaclass=abc.ABCMeta):
    """
    This is the interface for a game used within the MCTS search and mainly provides a forward simulator with methods
    for getting getting deep copies of your game state as well as sampling actions for exploration.

    :ivar seed: The seed used in all pseudo random components. This can be set and retrieved usind set_seed() and
    get_seed() only.
    """

    def __init__(self, seed):
        self.rand = numpy.random
        self.__seed = seed

    @abc.abstractmethod
    def legal_actions(self, simulation=False) -> list:
        """ Used in tree expansion. """
        pass

    @abc.abstractmethod
    def sample_action(self, simulation=False):
        """ Used in Roll outs. """
        pass

    @abc.abstractmethod
    def reset(self):
        """ (Re-)Initializes the Environment and returns the (new) initial state. """
        pass

    @abc.abstractmethod
    def step(self, action, simulation=False) -> tuple:
        """
        Take one step in the game. Similar to gym.env.step() this should output a tuple: observation, reward, done

        :param action: The action to be taken.
        :param simulation: The flag 'simulation' is True during MCTS steps and False by default. This can be used if you want a different
        behaviour during planning than during evaluation (e. g. plan in a different time step discretization).
        :return: observation, reward, done
        """
        pass

    @abc.abstractmethod
    def render(self, mode='human', **kwargs):
        """ Render the environment """
        pass

    @abc.abstractmethod
    def get_copy(self) -> "DeepCopyableGame":
        """ Returns a deep copy of your game. """
        pass

    def get_seed(self):
        """ Get the current seed. Note that we are using conventional getters and setters because this makes inheritance
         of getter/setter behaviour much more straight forward than using `@property`. We decided to put code
         readability over doing things the pythonic way in this case. """
        return self.__seed

    def set_seed(self, seed):
        """ Set the seed for all pseudo random components used in your game. """
        self.rand.seed(seed)
        self.__seed = seed


class GymGame(DeepCopyableGame, metaclass=abc.ABCMeta):
    """
    This abstract class underlies all classes that use OpenAI gym environments. It ensures that the Gym Environment
    is wrapped in the `DeepCopyableWrapper` and links the `DeepCopyableGame` methods to OpenAi gym.env's methods.
    """

    def __init__(self, env: gym.Env, seed=0):
        self.env = DeepCopyableWrapper(env) if not isinstance(env, DeepCopyableWrapper) else env
        self.render_copy = None
        super(GymGame, self).__init__(seed)

    def reset(self,seed=None):
        return self.env.reset(seed=seed)

    def close(self):
        self.env.close()
        if self.render_copy is not None:
            self.render_copy.close()

    def step(self, action, simulation=False):
        obs, rew, terminated, truncated, info = self.env.step(action)
        done = terminated or truncated
        return obs, rew, done 

    def render(self, mode='human', **kwargs):
        # This workaround is necessary because a game / a gym env that is rendering cannot be deepcopied
        if self.render_copy is None:
            self.render_copy = self.get_copy()
#             self.render_copy.env.render(mode, **kwargs)
            return self.render_copy.env.render()
        else:
            self.render_copy.close()
            self.render_copy = self.get_copy()
#             self.render_copy.env.render(mode, **kwargs)
            return self.render_copy.env.render()

    def get_copy(self) -> "GymGame":
        return GymGame(deepcopy(self.env), seed=self.rand.randint(1e9))

    def set_seed(self, seed):
        self.env.seed(seed)
        super(GymGame, self).set_seed(seed)

    def __str__(self):
        return str(self.env).split('<')[-1].split('>')[0].split(' ')[0]


class DiscreteGymGame(GymGame):

    def __init__(self, env, seed=0):
        assert isinstance(env.action_space, gym.spaces.Discrete), "Gym Env must have discrete action space!"
        super(DiscreteGymGame, self).__init__(env, seed)

    def step(self, action, simulation=False):
        action = int(action)
        obs, rew, done = super(DiscreteGymGame, self).step(action, simulation)
        return obs, rew, done

    def legal_actions(self, simulation=False):
        return [i for i in range(self.env.action_space.n)]

    def sample_action(self, simulation=False):
        legal_actions = self.legal_actions(simulation=simulation)
        return legal_actions[self.rand.random_integers(0, len(legal_actions) - 1)]

    def get_copy(self) -> "DiscreteGymGame":
        return DiscreteGymGame(deepcopy(self.env), self.rand.randint(1e9))


""" Continuous Actions """


class ContinuousGymGame(GymGame):

    def __init__(self, env, mu, sigma, seed=0):
        self.mu = mu
        self.sigma = sigma
        super(ContinuousGymGame, self).__init__(env, seed)

    def legal_actions(self, simulation=False) -> list:
        return [self.env.action_space.low, self.env.action_space.high]

    def sample_action(self, simulation=False):
        action = numpy.random.normal(self.mu, self.sigma)
        return numpy.clip(action, self.legal_actions(simulation)[0], self.legal_actions(simulation)[1])[0]

    def get_copy(self) -> "ContinuousGymGame":
        return ContinuousGymGame(deepcopy(self.env), self.mu, self.sigma, self.rand.randint(1e9))

    def step(self, action, simulation=False):
        return super(ContinuousGymGame, self).step([action], simulation)


class GymGameWithMacroActions(DiscreteGymGame):
    def __init__(self, env, seed, macro_actions: typing.List[typing.List[float]]):
        super(GymGameWithMacroActions, self).__init__(env, seed)
        self._macro_actions = macro_actions

    @property
    def macro_actions(self):
        return self._macro_actions

    def legal_actions(self, simulation=False):
        if simulation:
            # in simulation get the indexes of macro actions
            return [i for i in range(len(self.macro_actions))]
        else:
            # in evaluation get the indexes of the environment's action
            return [i for i in range(self.env.action_space.n)]

    def step(self, action, simulation=False):

        if simulation:
            # in simulation, traverse through the complete macro action
            reward = 0.
            mac_act = self.macro_actions[action]
            for a in mac_act:
                obs, rew, done , _ = super(GymGameWithMacroActions, self).step(a)
                reward += rew
            reward /= len(mac_act)  # return avg reward on macro action trajectory
        else:
            # in evaluation just take one step
            obs, reward, done, _ = super(GymGameWithMacroActions, self).step(action)

        return obs, reward, done

    def get_copy(self) -> "GymGameWithMacroActions":
        return GymGameWithMacroActions(
            deepcopy(self.env),
            seed=self.rand.randint(1e9),
            macro_actions=self.macro_actions
        )


class GymGameDoingMultipleStepsInSimulations(GymGameWithMacroActions):

    def __init__(self, env, seed=0, number_of_multiple_actions_in_simulation=1):
        self.n = number_of_multiple_actions_in_simulation
        self.env = env  # this is necessary so that self.legal_actions() works
        # macro actions are multiple actions i.e. >>> [[0, 0, 0, ...], [1, 1, 1, 1, ...], ...]
        macro_actions = [numpy.ones(self.n) * action for action in self.legal_actions()]
        super(GymGameDoingMultipleStepsInSimulations, self).__init__(env, seed, macro_actions)

    def get_copy(self) -> "GymGameDoingMultipleStepsInSimulations":
        return GymGameDoingMultipleStepsInSimulations(
            deepcopy(self.env),
            seed=self.rand.randint(1e9),
            number_of_multiple_actions_in_simulation=self.n
        )


class PendulumGameWithEngineeredMacroActions(GymGameWithMacroActions):

    def __init__(self, num_actions, action_damping, seed=0, max_macro_action_len=50):
        env = gym.make("Pendulum-v0")
        self.n_act = num_actions
        self.damping = action_damping
        env = DiscreteActionWrapper(env, num_actions=num_actions, damping=action_damping)
        self._max_macro_action_len = max_macro_action_len
        # macro actions are generated in each step
        super(PendulumGameWithEngineeredMacroActions, self).__init__(env=env, seed=seed, macro_actions=[])

    @property
    def macro_actions(self):
        macro_actions = []
        for action in super(PendulumGameWithEngineeredMacroActions, self).legal_actions(simulation=False):
            game_copy = self.get_copy()
            [cos_theta, sin_theta, theta_dot], _, done = game_copy.step(action)
            sign = numpy.sign(theta_dot)
            it = 1
            while sign == numpy.sign(theta_dot) and it <= self._max_macro_action_len and not done:
                [cos_theta, sin_theta, theta_dot], _, done = game_copy.step(action)
                it += 1
            macro_actions.append(numpy.ones(it) * action)
        return macro_actions

    def get_copy(self) -> "PendulumGameWithEngineeredMacroActions":
        copy = PendulumGameWithEngineeredMacroActions(num_actions=self.n_act,
                                                      action_damping=self.damping,
                                                      seed=self.rand.randint(1e9),
                                                      max_macro_action_len=self._max_macro_action_len)
        copy.env = deepcopy(self.env)
        return copy
