import ray
from rl_games.common.env_configurations import configurations
import numpy as np
import gym


class IVecEnv(object):
    def step(self, actions):
        raise NotImplementedError 

    def reset(self):
        raise NotImplementedError    

    def has_action_masks(self):
        return False

    def get_number_of_agents(self):
        return 1

    def get_env_info(self):
        pass


class IsaacEnv(IVecEnv):
    def __init__(self, config_name, num_actors, **kwargs):
        self.env = configurations[config_name]['env_creator'](**kwargs)
        self.obs = self.env.reset()
    
    def step(self, action):
        next_state, reward, is_done, info = self.env.step(action)
        next_state = self.reset()
        return next_state, reward, is_done, info

    def reset(self):
        self.obs = self.env.reset()
        return self.obs

    def get_env_info(self):
        info = {}
        info['action_space'] = self.env.action_space
        info['observation_space'] = self.env.observation_space
        return info


class RayWorker:
    def __init__(self, config_name, config):
        self.env = configurations[config_name]['env_creator'](**config)
        #self.obs = self.env.reset()

    def step(self, action):
        next_state, reward, is_done, info = self.env.step(action)
        
        if np.isscalar(is_done):
            episode_done = is_done
        else:
            episode_done = is_done.all()
        if episode_done:
            next_state = self.reset()
        if next_state.dtype == np.float64:
            next_state = next_state.astype(np.float32)
        return next_state, reward, is_done, info

    def render(self):
        self.env.render()

    def reset(self):
        self.obs = self.env.reset()
        return self.obs

    def get_action_mask(self):
        return self.env.get_action_mask()

    def get_number_of_agents(self):
        return self.env.get_number_of_agents()

    def get_env_info(self):
        info = {}
        observation_space = self.env.observation_space
        if isinstance(observation_space, gym.spaces.dict.Dict):
            observation_space = observation_space['observations']
        info['action_space'] = self.env.action_space
        info['observation_space'] = observation_space

        return info


class RayVecEnv(IVecEnv):
    def __init__(self, config_name, num_actors, **kwargs):
        self.config_name = config_name
        self.num_actors = num_actors
        self.use_torch = False
        self.remote_worker = ray.remote(RayWorker)
        self.workers = [self.remote_worker.remote(self.config_name, kwargs) for i in range(self.num_actors)]

    def step(self, actions):
        newobs, newrewards, newdones, newinfos = [], [], [], []
        res_obs = []
        for (action, worker) in zip(actions, self.workers):
            res_obs.append(worker.step.remote(action))
        all_res = ray.get(res_obs)
        for res in all_res:
            cobs, crewards, cdones, cinfos = res
            newobs.append(cobs)
            newrewards.append(crewards)
            newdones.append(cdones)
            newinfos.append(cinfos)
        return np.asarray(newobs, dtype=cobs.dtype), np.asarray(newrewards, dtype=np.float32), np.asarray(newdones, dtype=np.uint8), newinfos

    def get_env_info(self):
        res = self.workers[0].get_env_info.remote()
        return ray.get(res)

    def has_action_masks(self):
        return True

    def get_action_masks(self):
        mask = [worker.get_action_mask.remote() for worker in self.workers]
        return np.asarray(ray.get(mask), dtype=np.int32)

    def reset(self):
        obs = [worker.reset.remote() for worker in self.workers]
        return np.asarray(ray.get(obs))


class RayVecSMACEnv(IVecEnv):
    def __init__(self, config_name, num_actors, **kwargs):
        self.config_name = config_name
        self.num_actors = num_actors
        self.remote_worker = ray.remote(RayWorker)
        self.workers = [self.remote_worker.remote(self.config_name, kwargs) for i in range(self.num_actors)]
        res = self.workers[0].get_number_of_agents.remote()
        self.num_agents = ray.get(res)

    def get_env_info(self):
        res = self.workers[0].get_env_info.remote()
        return ray.get(res)

    def get_number_of_agents(self):
        return self.num_agents

    def step(self, actions):
        newobs, newrewards, newdones, newinfos = [], [], [], []
        res_obs = []
        for num, worker in enumerate(self.workers):
            res_obs.append(worker.step.remote(actions[self.num_agents*num: self.num_agents*num+self.num_agents]))

        for res in res_obs:
            cobs, crewards, cdones, cinfos = ray.get(res)
            newobs.append(cobs)
            newrewards.append(crewards)
            newdones.append(cdones)
            newinfos.append(cinfos)
        return np.concatenate(newobs, axis=0), np.concatenate(newrewards, axis=0), np.concatenate(newdones, axis=0), newinfos

    def has_action_masks(self):
        return True

    def get_action_masks(self):
        mask = [worker.get_action_mask.remote() for worker in self.workers]
        masks = ray.get(mask)
        return np.concatenate(masks, axis=0)

    def reset(self):
        obs = [worker.reset.remote() for worker in self.workers]
        newobs = ray.get(obs)
        return np.concatenate(newobs, axis=0)


vecenv_config = {}

def register(config_name, func):
    vecenv_config[config_name] = func

def create_vec_env(config_name, num_actors, **kwargs):
    vec_env_name = configurations[config_name]['vecenv_type']
    return vecenv_config[vec_env_name](config_name, num_actors, **kwargs)

register('RAY', lambda config_name, num_actors, **kwargs: RayVecEnv(config_name, num_actors, **kwargs))
register('RAY_SMAC', lambda config_name, num_actors, **kwargs: RayVecSMACEnv(config_name, num_actors, **kwargs))
register('ISAAC', lambda config_name, num_actors, **kwargs: IsaacEnv(config_name, num_actors, **kwargs))