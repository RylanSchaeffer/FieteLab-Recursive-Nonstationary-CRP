import os
import pandas as pd
import numpy as np
import joblib
import wandb


def download_wandb_project_runs_results(wandb_project_path: str,
                                        sweep_id: str = None,
                                        ) -> pd.DataFrame:
    # Download sweep results
    api = wandb.Api()

    # Project is specified by <entity/project-name>
    if sweep_id is None:
        runs = api.runs(path=wandb_project_path)
    else:
        runs = api.runs(path=wandb_project_path,
                        filters={"Sweep": sweep_id})

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
    finished_runs = sweep_results_df['State'] == 'finished'
    print(f"% of successfully finished runs: {finished_runs.mean()}")
    sweep_results_df = sweep_results_df[finished_runs]

    if sweep_id is not None:
        sweep_results_df = sweep_results_df[sweep_results_df['Sweep'] == sweep_id]

    # Ensure we aren't working with a slice.
    sweep_results_df = sweep_results_df.copy()

    return sweep_results_df


def generate_and_save_cluster_ratio_data(all_inf_algs_results_df: pd.DataFrame,
                                         sweep_results_dir_path: str):

    num_inferred_clusters_div_num_true_clusters_by_obs_idx = dict()
    num_inferred_clusters_div_total_num_true_clusters_by_obs_idx = dict()
    num_true_clusters_div_total_num_true_clusters_by_obs_idx = dict()

    num_inferred_clusters_div_num_true_clusters_by_obs_idx_df_path = os.path.join(
        sweep_results_dir_path,
        'num_inferred_clusters_div_num_true_clusters_by_obs_idx.csv')
    num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df_path = os.path.join(
        sweep_results_dir_path,
        'num_inferred_clusters_div_total_num_true_clusters_by_obs_idx.csv')
    num_true_clusters_div_total_num_true_clusters_by_obs_idx_df_path = os.path.join(
        sweep_results_dir_path,
        'num_true_clusters_div_total_num_true_clusters_by_obs_idx.csv')

    if not os.path.isfile(num_inferred_clusters_div_num_true_clusters_by_obs_idx_df_path) \
            or not os.path.isfile(num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df_path) \
            or not os.path.isfile(num_true_clusters_div_total_num_true_clusters_by_obs_idx_df_path):

        num_failed_loads = 0

        for inf_alg_results_joblib_path in all_inf_algs_results_df['inf_alg_results_path']:

            try:
                joblib_file = joblib.load(inf_alg_results_joblib_path)
            except TypeError:
                # Sometimes, the W&B path is NaN; don't know why. This throws a
                # TypeError: join() argument must be str or bytes, not 'float'
                # Just log these and continue
                print(f'Error: could not load {inf_alg_results_joblib_path}')
                num_failed_loads += 1
                continue

            # Obtain number of inferred clusters
            cluster_assignment_posteriors = joblib_file['inference_alg_results'][
                'cluster_assignment_posteriors']
            inferred_cluster_assignments = cluster_assignment_posteriors.argmax(axis=1)
            num_inferred_clusters_by_obs_idx = np.array([
                len(np.unique(inferred_cluster_assignments[:i + 1]))
                for i in range(len(inferred_cluster_assignments))])

            # Obtain numbers of observed and total true clusters
            true_cluster_assignments = joblib_file['mixture_model_results']['cluster_assignments']
            num_true_clusters_by_obs_idx = np.array([
                len(np.unique(true_cluster_assignments[:i + 1]))
                for i in range(len(true_cluster_assignments))])

            num_total_true_clusters = np.max(true_cluster_assignments)
            num_obs = true_cluster_assignments.shape[0]

            # Copy to ensure that Python can garbage-collect the joblib file pointers
            num_inferred_clusters_div_num_true_clusters_by_obs_idx[inf_alg_results_joblib_path] = \
                np.copy(num_inferred_clusters_by_obs_idx / num_true_clusters_by_obs_idx)
            num_inferred_clusters_div_total_num_true_clusters_by_obs_idx[inf_alg_results_joblib_path] = \
                np.copy(num_inferred_clusters_by_obs_idx / num_total_true_clusters)
            num_true_clusters_div_total_num_true_clusters_by_obs_idx[inf_alg_results_joblib_path] = \
                np.copy(num_true_clusters_by_obs_idx / num_total_true_clusters)

        # Each column name is an inf_alg_results_joblib_path
        # We want to transpose, then change the index to a column.
        # The resulting dataframes have column 1 with name inf_alg_results_path and the
        # remaining column names 0, 1, 2, ...
        num_inferred_clusters_div_num_true_clusters_by_obs_idx_df = pd.DataFrame.from_records(
                num_inferred_clusters_div_num_true_clusters_by_obs_idx,
                index=1 + np.arange(num_obs),
            ).T.rename_axis('inf_alg_results_path').reset_index()
        num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df = pd.DataFrame.from_records(
                num_inferred_clusters_div_total_num_true_clusters_by_obs_idx,
                index=1 + np.arange(num_obs),
            ).T.rename_axis('inf_alg_results_path').reset_index()
        num_true_clusters_div_total_num_true_clusters_by_obs_idx_df = pd.DataFrame.from_records(
                num_true_clusters_div_total_num_true_clusters_by_obs_idx,
                index=1 + np.arange(num_obs)
            ).T.rename_axis('inf_alg_results_path').reset_index()

        # Save dataframes
        num_inferred_clusters_div_num_true_clusters_by_obs_idx_df.to_csv(
            num_inferred_clusters_div_num_true_clusters_by_obs_idx_df_path,
            index=False)

        num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df.to_csv(
            num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df_path,
            index=False)

        num_true_clusters_div_total_num_true_clusters_by_obs_idx_df.to_csv(
            num_true_clusters_div_total_num_true_clusters_by_obs_idx_df_path,
            index=False)

        print(f'Fraction of failed loads: {num_failed_loads / len(all_inf_algs_results_df)}')

    else:
        # Load dataframes
        num_inferred_clusters_div_num_true_clusters_by_obs_idx_df = pd.read_csv(
            num_inferred_clusters_div_num_true_clusters_by_obs_idx_df_path,
            index_col=False)
        num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df = pd.read_csv(
            num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df_path,
            index_col=False)
        num_true_clusters_div_total_num_true_clusters_by_obs_idx_df = pd.read_csv(
            num_true_clusters_div_total_num_true_clusters_by_obs_idx_df_path,
            index_col=False)

    cluster_ratio_dfs_results = dict(
        num_inferred_clusters_div_num_true_clusters_by_obs_idx_df=num_inferred_clusters_div_num_true_clusters_by_obs_idx_df,
        num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df=num_inferred_clusters_div_total_num_true_clusters_by_obs_idx_df,
        num_true_clusters_div_total_num_true_clusters_by_obs_idx_df=num_true_clusters_div_total_num_true_clusters_by_obs_idx_df,
    )

    return cluster_ratio_dfs_results
