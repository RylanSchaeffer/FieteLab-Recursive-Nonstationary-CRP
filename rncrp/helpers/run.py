import logging
import numpy as np
import os
import pandas as pd
import sys
import torch
from timeit import default_timer as timer
from typing import Dict, List, Tuple
import wandb

from rncrp.inference import VariationalInferenceGMM


def create_logger(run_dir):

    logging.basicConfig(
        filename=os.path.join(run_dir, 'logging.log'),
        level=logging.DEBUG)

    logging.info('Logger created successfully')

    # also log to std out
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(console_handler)

    # disable matplotlib font warnings
    logging.getLogger("matplotlib").setLevel(logging.ERROR)


def download_wandb_project_runs_results(wandb_project_path: str,
                                        sweep_name: str = None,
                                        ) -> pd.DataFrame:

    # Download sweep results
    api = wandb.Api()

    # Project is specified by <entity/project-name>
    runs = api.runs(path=wandb_project_path)

    sweep_results_list = []
    for run in runs:
        # .summary contains the output keys/values for metrics like accuracy.
        #  We call ._json_dict to omit large files
        summary = run.summary._json_dict

        # .config contains the hyperparameters.
        #  We remove special values that start with _.
        summary.update(
            {k: v for k, v in run.config.items()
             if not k.startswith('_')})

        summary.update({'State': run.state,
                        'Sweep': run.sweep.id if run.sweep is not None else None})
        # .name is the human-readable name of the run.
        summary.update({'run_name': run.name})
        sweep_results_list.append(summary)

    sweep_results_df = pd.DataFrame(sweep_results_list)

    # Keep only finished runs
    sweep_results_df = sweep_results_df[sweep_results_df['State'] == 'finished']

    if sweep_name is not None:
        sweep_results_df = sweep_results_df[sweep_results_df['Sweep'] == sweep_name]

    sweep_results_df = sweep_results_df.copy()

    return sweep_results_df


def run_inference_alg(inference_alg_str: str,
                      observations: np.ndarray,
                      observations_times: np.ndarray,
                      gen_model_params: Dict[str, Dict[str, float]],
                      inference_alg_kwargs: Dict = None):

    if inference_alg_str == 'RN-CRP':
        if inference_alg_kwargs is None:
            inference_alg_kwargs = dict()

        inference_alg = RNCRP()
    elif inference_alg_str.startswith('DP-Means'):
        if inference_alg_kwargs is None:
            inference_alg_kwargs = dict()

        inference_alg = DPMeans()
        if inference_alg_str.endswith('(offline)'):
            inference_alg_kwargs['num_passes'] = 8  # same as Kulis and Jordan
        elif inference_alg_str.endswith('(online)'):
            inference_alg_kwargs['num_passes'] = 1
        else:
            raise ValueError('Invalid DP Means')
    elif inference_alg_str == 'VI-GMM':
        if inference_alg_kwargs is None:
            inference_alg_kwargs = dict()

        inference_alg = VariationalInferenceGMM(
            gen_model_params=gen_model_params,
            inference_alg_kwargs=inference_alg_kwargs)
    else:
        raise ValueError(f'Unknown inference algorithm: {inference_alg_str}')

    # Run inference algorithm
    # time using timer because https://stackoverflow.com/a/25823885/4570472
    start_time = timer()
    inference_alg_results = inference_alg.fit(
        observations=observations,
        observations_times=observations_times,
    )
    stop_time = timer()
    runtime = stop_time - start_time
    inference_alg_results['Runtime'] = runtime

    # Add inference alg object to results, for later generating predictions
    inference_alg_results['inference_alg'] = inference_alg

    return inference_alg_results


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)