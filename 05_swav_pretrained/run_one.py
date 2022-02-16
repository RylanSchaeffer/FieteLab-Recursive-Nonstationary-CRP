"""
Perform inference on SwAV ImageNet embeddings for the specified inference
algorithm and model parameters.

Example usage:

05_swav_pretrained/run_one.py
"""

import joblib
import numpy as np
import os
import wandb

# import plot
import rncrp.data.real
import rncrp.helpers.dynamics
import rncrp.helpers.run
import rncrp.metrics

config_defaults = {
    'inference_alg_str': 'Dynamical-CRP',
    'dynamics_str': 'step',
    'dynamics_a': 1.,
    'dynamics_b': 0.,
    'alpha': 1.1,
    'beta': 0.,
    'likelihood_kappa': 1.,
    'repeat_idx': 0,
}

wandb.init(project='dcrp-swav-pretrained',
           config=config_defaults)
config = wandb.config

print(f'Running:')
for key, value in config.items():
    print(key, ' : ', value)

# determine paths
exp_dir = '05_swav_pretrained'
results_dir_path = os.path.join(exp_dir, 'results')
os.makedirs(results_dir_path, exist_ok=True)
inf_alg_results_path = os.path.join(results_dir_path,
                                    f'id={wandb.run.id}.joblib')
wandb.log({'inf_alg_results_path': inf_alg_results_path},
          step=0)

# set seeds
rncrp.helpers.run.set_seed(seed=config['repeat_idx'])

mixture_model_results = rncrp.data.real.load_dataset(
    dataset_name='swav_imagenet_2021')

gen_model_params = {
    'mixing_params': {
        'alpha': config['alpha'],
        'beta': config['beta'],
        'dynamics_str': config['dynamics_str'],
        'dynamics_params': mixture_model_results['dynamics_params']
    },
    'feature_prior_params': {
        # 'centroids_prior_cov_prefactor': config['centroids_prior_cov_prefactor']
    },
    'likelihood_params': {
        'distribution': 'vonmises_fisher',
        'likelihood_kappa': config['likelihood_kappa']
    }
}

inference_alg_results = rncrp.helpers.run.run_inference_alg(
    inference_alg_str=config['inference_alg_str'],
    observations=mixture_model_results['observations'],
    observations_times=mixture_model_results['observations_times'],
    gen_model_params=gen_model_params,
)

scores, map_cluster_assignments = rncrp.metrics.compute_predicted_clusters_scores(
    cluster_assignment_posteriors=inference_alg_results['cluster_assignment_posteriors'],
    true_cluster_assignments=mixture_model_results['cluster_assignments'],
)
inference_alg_results.update(scores)
inference_alg_results['map_cluster_assignments'] = map_cluster_assignments
wandb.log(scores, step=0)

sum_sqrd_distances = rncrp.metrics.compute_sum_of_squared_distances_to_nearest_center(
    X=mixture_model_results['observations'],
    centroids=inference_alg_results['inference_alg'].centroids_after_last_obs())
inference_alg_results['training_reconstruction_error'] = sum_sqrd_distances
wandb.log({'training_reconstruction_error': sum_sqrd_distances}, step=0)


data_to_store = dict(
    config=dict(config),  # Need to convert WandB config to proper dict
    inference_alg_results=inference_alg_results,
    scores=scores)

joblib.dump(data_to_store,
            filename=inf_alg_results_path)

print('Finished run.')
