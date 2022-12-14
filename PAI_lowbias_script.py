# -*- coding: utf-8 -*-
"""
Created during November & December 2022
by authors Kevin Hilbert, Charlotte Meinke & Silvan Hornstein
"""

import copy
import csv
import math
import mkl
import multiprocessing
import os
import sklearn
import statistics
import sys
import time
import warnings
from multiprocessing import Pool
import numpy as np
import pandas as pd
from pandas import read_csv
from sklearn.compose import ColumnTransformer
from sklearn.experimental import enable_iterative_imputer
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer, IterativeImputer
from sklearn.linear_model import BayesianRidge, ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.metrics.pairwise import pairwise_distances
from sklearn.model_selection import StratifiedKFold
from sklearn import preprocessing


"""
How to use this script

Data preparation:

    Define a working directory and met this wunder path_workingdirectory

    Prepare the data: this script takes tab-delimited text files as input for features, labels and group membership (i.e. treatment arm). Usually, tab-delimited text can easily be exported from statistic programs or excel
    Make sure that the group membership file codes the groups as number, for instance 0 for CBT and 1 for SSRI
    Make sure that categorical variables are one-hot encoded as binaries, and these binaries are scaled to 0.5 and -0.5

    Make sure the data in these text files uses a point as decimal separator and variable names do not include special characters
    The script assumes that all text files include the variable name in the top line
    Save the feature, label and group data in a subfolder 'data' under your working directory

    Missing Values: this script uses MICE to impute missing for dimensional features and mode imputation for binary features. Consequently, missings must be differentially coded depending on type. Please code a missing dimensional value as 999999 and a missing binary value as 777777


Script preparation:
    Name your model in options_overall['name_model'] - this will be used to name all outputs by the script
    Set the number of total iterations under options_overall['number_iterations']
    Set the of folds for the k-fold under options_overall['number_folds']
    Give the names of your text files including features, labels and group membership under options_overall['name_features'], options_overall['name_labels'] , options_overall['name_groups_id']
    Use map or pool.map at the end of the script depending on whether you run this on your local computer or on a cluster
"""



"""
Empirical and theoretical foundations of design choices

There are plenty of different options for preparing the data and the machine learning pipeline. Mostly, no clear data is available suggesting which approches are superior to others. Still, there were some papers that we considered important when designing this pipeline, which are presented below:

Centering of variables and centering of binary variables to -0.5 and 0.5 -- Kraemer & Blasey (2004). Centring in regression analyses: a strategy to prevent errors in statistical inference. Int J Methods Psychiatr Res, 13(3), 141-51.
Elastic net feature reduction -- Bennemann et al. (2022). Predicting patients who will drop out of out-patient psychotherapy using machine learning algorithms. The British Journal of Psychiatry, 220, 192???201
Random Forest -- Grinsztajn et al (preprint). Why do tree-based models still outperform deep learning on tabular data? arXiv, 2207.08815.
Refraining from LOO-CV and using a repeated 5-fold stratified train-test split -- Varoquaux (2018). Cross-validation failure: Small sample sizes lead to large error bars. Neuroimage, 180(A), 68-77.
     & Varoquaux et al. (2017). Assessing and tuning brain decoders: Cross-validation, caveats, and guidelines. NeuroImage, 145, 166???179.
     & Flint et al. (2021). Systematic misestimation of machine learning performance in neuroimaging studies of depression. Neuropsychopharmacology, 46,??1510???1517.
     & the observation that prediction performance varies substantially between iterations in our own previous papers, including
     Leehr et al. (2021). Clinical predictors of treatment response towards exposure therapy in virtuo in spider phobia: a machine 	learning and external cross-validation approach. Journal of Anxiety Disorders, 83, 102448.
     & Hilbert et al. (2021). Identifying CBT non-response among OCD outpatients: a machine-learning approach. Psychotherapy Research, 31(1), 52-62.
"""


start_time = time.time()
mkl.set_num_threads(1)

PATH_WORKINGDIRECTORY = 'your_path\\' 

OPTIONS_OVERALL = {'name_model': 'name_your_model'}
OPTIONS_OVERALL['number_iterations'] = 100
OPTIONS_OVERALL['number_folds'] = 5
OPTIONS_OVERALL['name_features'] = 'features.txt'
OPTIONS_OVERALL['name_labels'] = 'labels.txt'
OPTIONS_OVERALL['name_groups_id'] = 'groups_id.txt'


def create_folders():
    """Folder for results are created, in case the folder already exists the script stops to avoid wrong results """
    if not os.path.exists(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'])):
        os.makedirs(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model']))
        os.makedirs(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'accuracy'))
        os.makedirs(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'individual_rounds'))
    elif os.path.exists(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'])):
        print('Please use a new model name or delete existing analysis')
        sys.exit("Execution stopped")


def do_iterations(numrun):
    """Runs a whole iteration of the sklearn pipeline and following calculation of the PAI score"""
    global PATH_WORKINGDIRECTORY, OPTIONS_OVERALL

    random_state_seed = numrun
    print('The current run is iteration {}.'.format(numrun))


    # Import Data und Labels
    features_import_path = os.path.join(PATH_WORKINGDIRECTORY,'data',OPTIONS_OVERALL['name_features'])
    labels_import_path = os.path.join(PATH_WORKINGDIRECTORY,'data',OPTIONS_OVERALL['name_labels'])
    name_groups_id_import_path = os.path.join(PATH_WORKINGDIRECTORY,'data',OPTIONS_OVERALL['name_groups_id'])
    features_import = read_csv(features_import_path, sep="\t", header=0)
    labels_import = read_csv(labels_import_path, sep="\t", header=0)
    name_groups_id_import = read_csv(name_groups_id_import_path, sep="\t", header=0)


    # Prepare variables to save outcomes
    skf = StratifiedKFold(n_splits=OPTIONS_OVERALL['number_folds'], shuffle=True, random_state=random_state_seed)
    X = features_import
    y = labels_import
    cvs = 0

    results_all_cvs = {
        "correlation_all_cvs" : np.zeros((OPTIONS_OVERALL['number_folds'],2)),
        "RMSE_all_cvs" : np.zeros((OPTIONS_OVERALL['number_folds'],2)),
        "MAE_all_cvs" : np.zeros((OPTIONS_OVERALL['number_folds'],2)),
        "pai_all_cvs_tx_alternative1" : [],
        "pai_all_cvs_tx_alternative0" : [],
        "abspai_all_cvs_tx_alternative1" : [],
        "abspai_all_cvs_tx_alternative0" : [],
        "pai_all_cvs_50_percent_tx_alternative1" : [],
        "pai_all_cvs_50_percent_tx_alternative0" : [],
        "abspai_all_cvs_50_percent_tx_alternative1" : [],
        "abspai_all_cvs_50_percent_tx_alternative0" : [],
        "obs_outcomes_optimal_all_cvs_tx_alternative1" : [],
        "obs_outcomes_optimal_all_cvs_tx_alternative0" : [],
        "obs_outcomes_nonoptimal_all_cvs_tx_alternative1" : [],
        "obs_outcomes_nonoptimal_all_cvs_tx_alternative0" : [],
        "obs_outcomes_optimal_all_cvs_50_percent_tx_alternative1" : [],
        "obs_outcomes_optimal_all_cvs_50_percent_tx_alternative0" : [],
        "obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative1" : [],
        "obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative0" : [],
        "feature_importances_all_cvs_tx_alternative1" : np.zeros((5, X.shape[1])),
        "feature_importances_all_cvs_tx_alternative0" : np.zeros((5, X.shape[1]))
        }

    # Perform train-test split
    for train_index, test_index in skf.split(X, name_groups_id_import):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]


        # Data exclusion
        X_train_cleaned, X_test_cleaned, features_index_copy, features_excluded = exclude_features(X_train, X_test)


        # Split treatment groups
        X_tx_alternative1_train = X_train_cleaned.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 1]
        X_tx_alternative1_test = X_test_cleaned.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 1]
        X_tx_alternative0_train = X_train_cleaned.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 0]
        X_tx_alternative0_test = X_test_cleaned.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 0]
        y_tx_alternative1_train = y_train.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 1]
        y_tx_alternative1_test = y_test.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 1]
        y_tx_alternative0_train = y_train.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 0]
        y_tx_alternative0_test = y_test.loc[name_groups_id_import[name_groups_id_import.columns[0]] == 0]


        # Imputation missing values
        X_tx_alternative1_train_imputed, X_tx_alternative1_test_imputed = mice_mode_imputation(X_tx_alternative1_train, X_tx_alternative1_test, random_state_seed)
        X_tx_alternative0_train_imputed, X_tx_alternative0_test_imputed = mice_mode_imputation(X_tx_alternative0_train, X_tx_alternative0_test, random_state_seed)


        # Scaling
        X_tx_alternative1_train_imputed_scaled, X_tx_alternative1_test_imputed_scaled = z_scaling(X_tx_alternative1_train_imputed, X_tx_alternative1_test_imputed)
        X_tx_alternative0_train_imputed_scaled, X_tx_alternative0_test_imputed_scaled = z_scaling(X_tx_alternative0_train_imputed, X_tx_alternative0_test_imputed)


        # Feature Selection with Elastic net
        y_tx_alternative1_train=np.ravel(y_tx_alternative1_train)
        y_tx_alternative0_train=np.ravel(y_tx_alternative0_train)

        # Alternative 1
        clf_elastic_tx_alternative1 = ElasticNet(alpha=1.0, l1_ratio=0.5, fit_intercept=False,
                                                 max_iter=1000, tol=0.0001, random_state=random_state_seed, selection='cyclic')
        sfm_tx_alternative1 = SelectFromModel(clf_elastic_tx_alternative1, threshold="mean")
        sfm_tx_alternative1.fit(X_tx_alternative1_train_imputed_scaled, y_tx_alternative1_train)

        # Alternative 0
        clf_elastic_tx_alternative0 = ElasticNet(alpha=1.0, l1_ratio=0.5, fit_intercept=False,
                                                 max_iter=1000, tol=0.0001, random_state=random_state_seed, selection='cyclic')
        sfm_tx_alternative0 = SelectFromModel(clf_elastic_tx_alternative0, threshold="mean")
        sfm_tx_alternative0.fit(X_tx_alternative0_train_imputed_scaled, y_tx_alternative0_train)


        # Feature Selection Factual
        X_tx_alternative1_train_imputed_scaled_selected_factual = sfm_tx_alternative1.transform(X_tx_alternative1_train_imputed_scaled)
        X_tx_alternative1_test_imputed_scaled_selected_factual = sfm_tx_alternative1.transform(X_tx_alternative1_test_imputed_scaled)
        X_tx_alternative0_train_imputed_scaled_selected_factual = sfm_tx_alternative0.transform(X_tx_alternative0_train_imputed_scaled)
        X_tx_alternative0_test_imputed_scaled_selected_factual = sfm_tx_alternative0.transform(X_tx_alternative0_test_imputed_scaled)


        # Feature Selection Counterfactual
        X_tx_alternative1_test_imputed_scaled_selected_counterfactual = sfm_tx_alternative0.transform(X_tx_alternative1_test_imputed_scaled)
        X_tx_alternative0_test_imputed_scaled_selected_counterfactual = sfm_tx_alternative1.transform(X_tx_alternative0_test_imputed_scaled)


        # Prediction with Ridge Regression
        y_tx_alternative1_train = np.ravel(y_tx_alternative1_train)
        y_tx_alternative0_train = np.ravel(y_tx_alternative0_train)
        y_tx_alternative1_test = np.ravel(y_tx_alternative1_test)
        y_tx_alternative0_test = np.ravel(y_tx_alternative0_test)

        clf_tx_alternative1 = Ridge(fit_intercept=False, copy_X=True, positive=False)
        clf_tx_alternative1.fit(X_tx_alternative1_train_imputed_scaled_selected_factual, y_tx_alternative1_train)
        clf_tx_alternative0 = Ridge(fit_intercept=False, copy_X=True, positive=False)
        clf_tx_alternative0.fit(X_tx_alternative0_train_imputed_scaled_selected_factual, y_tx_alternative0_train)

        y_prediction_tx_alternative1 = pd.DataFrame()
        y_prediction_tx_alternative1["y_pred_factual"] = clf_tx_alternative1.predict(X_tx_alternative1_test_imputed_scaled_selected_factual)
        y_prediction_tx_alternative1["y_true"] = y_tx_alternative1_test[:]
        y_prediction_tx_alternative1["y_pred_counterfactual"] = clf_tx_alternative0.predict(X_tx_alternative1_test_imputed_scaled_selected_counterfactual)

        y_prediction_tx_alternative0 = pd.DataFrame()
        y_prediction_tx_alternative0["y_pred_factual"] = clf_tx_alternative0.predict(X_tx_alternative0_test_imputed_scaled_selected_factual)
        y_prediction_tx_alternative0["y_true"] = y_tx_alternative0_test[:]
        y_prediction_tx_alternative0["y_pred_counterfactual"] = clf_tx_alternative1.predict(X_tx_alternative0_test_imputed_scaled_selected_counterfactual)


        # Results Processing

        # Get importances for each feature
        # Alternative 1
        feature_importances_tx_alternative1 = copy.deepcopy(features_excluded)
        feature_importances_tx_alternative1[feature_importances_tx_alternative1==1]=np.nan

        counter_features_selected_tx_alternative1 = 0
        for number_features_tx_alternative1 in range(len(sfm_tx_alternative1.get_support())):
            if sfm_tx_alternative1.get_support()[number_features_tx_alternative1] == True:
                feature_importances_tx_alternative1[features_index_copy[number_features_tx_alternative1]] = clf_tx_alternative1.coef_[counter_features_selected_tx_alternative1]

                counter_features_selected_tx_alternative1 = counter_features_selected_tx_alternative1 + 1
            else:
                feature_importances_tx_alternative1[features_index_copy[number_features_tx_alternative1]] = 0

        # Alternative 0
        feature_importances_tx_alternative0 = copy.deepcopy(features_excluded)
        feature_importances_tx_alternative0[feature_importances_tx_alternative0==1]=np.nan

        counter_features_selected_tx_alternative0 = 0
        for number_features_tx_alternative0 in range(len(sfm_tx_alternative0.get_support())):
            if sfm_tx_alternative0.get_support()[number_features_tx_alternative0] == True:
                feature_importances_tx_alternative0[features_index_copy[number_features_tx_alternative0]] = clf_tx_alternative0.coef_[counter_features_selected_tx_alternative0]
                counter_features_selected_tx_alternative0 = counter_features_selected_tx_alternative0 + 1
            else:
                feature_importances_tx_alternative0[features_index_copy[number_features_tx_alternative0]] = 0


        results_metrics_alternative1 = result_metrics(y_prediction_tx_alternative1)
        results_metrics_alternative0 = result_metrics(y_prediction_tx_alternative0)

        # Create an overview for values of both treatments across FOLDS
        results_all_cvs["correlation_all_cvs"][cvs,0] = results_metrics_alternative1["correlation"]
        results_all_cvs["correlation_all_cvs"][cvs,1] =  results_metrics_alternative0["correlation"]
        results_all_cvs["RMSE_all_cvs"][cvs,0] = results_metrics_alternative1["RMSE"]
        results_all_cvs["RMSE_all_cvs"][cvs,1] = results_metrics_alternative0["RMSE"]
        results_all_cvs["MAE_all_cvs"][cvs,0] = results_metrics_alternative1["MAE"]
        results_all_cvs["MAE_all_cvs"][cvs,1] = results_metrics_alternative0["MAE"]

        results_all_cvs["pai_all_cvs_tx_alternative1"].append(results_metrics_alternative1["pai"])
        results_all_cvs["pai_all_cvs_tx_alternative0"].append(results_metrics_alternative0["pai"])
        results_all_cvs["abspai_all_cvs_tx_alternative1"].append(results_metrics_alternative1["abspai"])
        results_all_cvs["abspai_all_cvs_tx_alternative0"].append(results_metrics_alternative0["abspai"])
        results_all_cvs["obs_outcomes_optimal_all_cvs_tx_alternative1"].append(results_metrics_alternative1["obs_outcomes_optimal"])
        results_all_cvs["obs_outcomes_optimal_all_cvs_tx_alternative0"].append(results_metrics_alternative0["obs_outcomes_optimal"])
        results_all_cvs["obs_outcomes_nonoptimal_all_cvs_tx_alternative1"].append(results_metrics_alternative1["obs_outcomes_nonoptimal"])
        results_all_cvs["obs_outcomes_nonoptimal_all_cvs_tx_alternative0"].append(results_metrics_alternative0["obs_outcomes_nonoptimal"])

        results_all_cvs["feature_importances_all_cvs_tx_alternative1"][cvs] = feature_importances_tx_alternative1.T
        results_all_cvs["feature_importances_all_cvs_tx_alternative0"][cvs] = feature_importances_tx_alternative0.T

        results_all_cvs["pai_all_cvs_50_percent_tx_alternative1"].append(results_metrics_alternative1["pai_50_percent"])
        results_all_cvs["pai_all_cvs_50_percent_tx_alternative0"].append(results_metrics_alternative0["pai_50_percent"])
        results_all_cvs["abspai_all_cvs_50_percent_tx_alternative1"].append(results_metrics_alternative1["abspai_50_percent"])
        results_all_cvs["abspai_all_cvs_50_percent_tx_alternative0"].append(results_metrics_alternative0["abspai_50_percent"])
        results_all_cvs["obs_outcomes_optimal_all_cvs_50_percent_tx_alternative1"].append(results_metrics_alternative1["obs_outcomes_optimal_pai_50_percent"])
        results_all_cvs["obs_outcomes_optimal_all_cvs_50_percent_tx_alternative0"].append(results_metrics_alternative0["obs_outcomes_optimal_pai_50_percent"])
        results_all_cvs["obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative1"].append(results_metrics_alternative1["obs_outcomes_nonoptimal_pai_50_percent"])
        results_all_cvs["obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative0"].append(results_metrics_alternative0["obs_outcomes_nonoptimal_pai_50_percent"])

        cvs = cvs + 1

    # Concatenate results per list of numpy arrays
    for key in results_all_cvs:
        if key not in ("correlation_all_cvs","RMSE_all_cvs","MAE_all_cvs", "feature_importances_all_cvs_tx_alternative0","feature_importances_all_cvs_tx_alternative1"):
            results_all_cvs[key] = np.concatenate(results_all_cvs[key], axis=0)
    # Concatenate results across treatments
    results_all_cvs_all = {}
    for key_alt1 in results_all_cvs:
        if key_alt1.endswith("alternative1") and not key_alt1.startswith("feature"):
            key_alt0 = key_alt1.replace("alternative1","alternative0")
            key_all = key_alt1.replace("_tx_alternative1","_all")
            results_all_cvs_all[key_all] = np.concatenate((results_all_cvs[key_alt1],results_all_cvs[key_alt0]),axis = 0)
    results_all_cvs.update(results_all_cvs_all)

    results_all_cv_sum = {}
    # Calculate mean values for all variables
    for key in results_all_cvs:
        if not key.startswith("feature"):
            if key in ("correlation_all_cvs","RMSE_all_cvs","MAE_all_cvs"):
                new_key_name = key.replace("all_cvs", "all_cv_sum_all")
            else:
                new_key_name = key.replace("all_cvs", "all_cv_sum")
            results_all_cv_sum[new_key_name] = np.mean(results_all_cvs[key])

    # Calculate Cohen??s d
    def cohens_d(x,y):
        """Cohens D is calculated"""
        d = (statistics.mean(x) - statistics.mean(y)) / math.sqrt((statistics.stdev(x) ** 2 + statistics.stdev(y) ** 2)/2)
        return d
    results_all_cv_sum["cohens_d_tx_alternative1"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_tx_alternative1"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_tx_alternative1"])
    results_all_cv_sum["cohens_d_tx_alternative0"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_tx_alternative0"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_tx_alternative0"])
    results_all_cv_sum["cohens_d_all"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_all"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_all"])
    results_all_cv_sum["cohens_d_50_percent_tx_alternative1"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_50_percent_tx_alternative1"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative1"])
    results_all_cv_sum["cohens_d_50_percent_tx_alternative0"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_50_percent_tx_alternative0"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_50_percent_tx_alternative0"])
    results_all_cv_sum["cohens_d_50_percent_all"] = cohens_d(x = results_all_cvs["obs_outcomes_optimal_all_cvs_50_percent_all"],y = results_all_cvs["obs_outcomes_nonoptimal_all_cvs_50_percent_all"])

    # Save results of each result-metric in file
    save_results(results_all_cv_sum)

    # Feature importances
    # Alternative 1
    feature_importances_all_cv_sum_tx_alternative1 = np.nanmean(results_all_cvs["feature_importances_all_cvs_tx_alternative1"], axis = 0)
    feature_importances_all_cv_sum_nans_tx_alternative1 = sum(np.isnan(results_all_cvs["feature_importances_all_cvs_tx_alternative1"]))
    feature_importances_all_cv_sum_nonzero_tx_alternative1 = np.count_nonzero(results_all_cvs["feature_importances_all_cvs_tx_alternative1"], axis=0)-sum(np.isnan(results_all_cvs["feature_importances_all_cvs_tx_alternative1"]))
    # Alternative 0
    feature_importances_all_cv_sum_tx_alternative0 = np.nanmean(results_all_cvs["feature_importances_all_cvs_tx_alternative0"], axis = 0)
    feature_importances_all_cv_sum_nans_tx_alternative0 = sum(np.isnan(results_all_cvs["feature_importances_all_cvs_tx_alternative0"]))
    feature_importances_all_cv_sum_nonzero_tx_alternative0 = np.count_nonzero(results_all_cvs["feature_importances_all_cvs_tx_alternative0"], axis=0)-sum(np.isnan(results_all_cvs["feature_importances_all_cvs_tx_alternative0"]))

    save_features(feature_importances_all_cv_sum_tx_alternative1,feature_importances_all_cv_sum_tx_alternative0,feature_importances_all_cv_sum_nans_tx_alternative1,feature_importances_all_cv_sum_nans_tx_alternative0,feature_importances_all_cv_sum_nonzero_tx_alternative1,feature_importances_all_cv_sum_nonzero_tx_alternative0)


def save_results(results_dict_func):
    """Results are saved for the individual round in the defined working directory."""
    for key in results_dict_func:

        save_option = os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'individual_rounds',(OPTIONS_OVERALL['name_model'] + '_per_iteration_' + str(key) + '.txt'))

        with open(save_option,'a', newline='') as fd:
            writer = csv.writer(fd,delimiter=',')
            writer.writerow([str(results_dict_func[key])])


def save_features(*argv):
    """Features are saved for the individual rounds in the defined working directory"""
    varnames=list(('feature_importances_all_cv_sum_tx_alternative1','feature_importances_all_cv_sum_tx_alternative0','feature_importances_all_cv_sum_NaNs_tx_alternative1','feature_importances_all_cv_sum_NaNs_tx_alternative0','feature_importances_all_cv_sum_nonzero_tx_alternative1','feature_importances_all_cv_sum_nonzero_tx_alternative0'))
    counter=0

    for arg in argv:

        save_option = os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'individual_rounds',(OPTIONS_OVERALL['name_model'] + '_per_iteration_' + str(varnames[counter]) + '.txt' ))

        with open(save_option,'a', newline='') as fd:
            writer = csv.writer(fd,delimiter=',')
            writer.writerow(arg)

        counter=counter+1


def exclude_features(X_train, X_test):
    """
    A two-step procedure to exclude features

    Step 1:
    Features are excluded if
        no variance is present in it
        more than 10% of values are missing
        less than 10% of values are in the least common category (binary features only)

    Step2:
    Correlations between dimensional features and jaccard similarity between binary features are calculated
    Features are excluded if correlation or jaccard similarity is >0.8, based on which of the two features has the largest overall correlation or jaccard similarity with other features
    """

    X_train_NA = X_train.replace(999999, np.NaN)
    X_train_NA = X_train_NA.replace(777777, np.NaN)

    features_excluded = np.zeros((X_train_NA.shape[1]))

    for varindex in range(X_train_NA.shape[1]):
        if np.std(X_train_NA.iloc[:,varindex],axis=0) == 0: #no variance in variable
            features_excluded[varindex] = 1
        if X_train_NA.iloc[:,varindex].isna().sum() > (len(X_train_NA)/10): #more than 10% missings
            features_excluded[varindex] = 1
        if X_train_NA.iloc[:,varindex].nunique(dropna = True) == 2: #categorial: less than 10% of values in least common category (binary)
            if min(X_train_NA.iloc[:,varindex].value_counts()) < (len(X_train_NA)/10):
                features_excluded[varindex] = 1

    # Correlations between variables > 0.8 or Jaccard similarity betweeen variables > 0.8
    X_train_NA_features_index = np.array(list(range(X_train_NA.shape[1])))

    # Create dataframes for dimensional and binary variables (sets variables to NA)
    X_train_NA_dim = copy.deepcopy(X_train_NA)
    X_train_NA_bin = copy.deepcopy(X_train_NA)
    for varindex in range(0, X_train_NA.shape[1]):
        if X_train_NA.iloc[:,varindex].nunique(dropna = True) == 2:
            X_train_NA_dim.iloc[:,varindex] = np.nan
        if X_train_NA.iloc[:,varindex].nunique(dropna = True) > 2:
            X_train_NA_bin.iloc[:,varindex] = np.nan


    # Dimensional variables: Correlation > 0.8
    stopper = False
    while stopper == False: # uses while loop to exclude features until no correlation > 0.8
        X_train_NA_copy = copy.deepcopy(X_train_NA_dim.loc[:, (features_excluded == 0)])
        X_train_NA_features_index_copy = copy.deepcopy(X_train_NA_features_index[features_excluded == 0])
        cors = np.array(X_train_NA_copy.corr())
        np.fill_diagonal(cors, np.nan)
        with warnings.catch_warnings(): # Ignore warning when calculating mean only over NAs
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mean_corr = np.nanmean(abs(cors),axis=1)
        if np.nanmax(abs(cors)) > 0.80:
            feature_pair_high_cor_idx = np.where(abs(cors)==np.nanmax(abs(cors)))
            try:
                if mean_corr[feature_pair_high_cor_idx[0]] > mean_corr[feature_pair_high_cor_idx[1]]:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[0]]] = 1
                else:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[1]]] = 1
            except:
                feature_pair_high_cor_idx = feature_pair_high_cor_idx[0]
                if mean_corr[feature_pair_high_cor_idx[0]] > mean_corr[feature_pair_high_cor_idx[1]]:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[0]]] = 1
                else:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[1]]] = 1
        else:
            stopper = True

    # Binary variables: Jaccard similarity > 0.8
    stopper = False
    while stopper == False: # uses while loop to exclude features until no jaccard similarity > 0.8
        X_train_NA_copy = copy.deepcopy(X_train_NA_bin.loc[:, (features_excluded == 0)])
        X_train_NA_features_index_copy = copy.deepcopy(X_train_NA_features_index[features_excluded == 0])

        jac_sim = 1 - pairwise_distances(X_train_NA_copy.T, metric = "hamming", force_all_finite="allow-nan")
        # Set jac_sim to NA for columns and rows that included only NAs (dimensional variables) (These variables have a jaccard similarity of 0)
        for var_idx in range(0,X_train_NA_copy.shape[1]):
            if X_train_NA_copy.iloc[:,var_idx].nunique() == 0 and pd.isna(pd.unique(X_train_NA_copy.iloc[:,var_idx])[0]):
                jac_sim[:,var_idx] = np.nan
                jac_sim[var_idx,:] = np.nan
        np.fill_diagonal(jac_sim, np.nan)
        with warnings.catch_warnings(): # Ignore warning when calculating mean only over NAs
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mean_jac_sim = np.nanmean(abs(jac_sim),axis=1)
        if np.nanmax(abs(jac_sim)) > 0.8:
            feature_pair_high_cor_idx = np.where(abs(jac_sim)==np.nanmax(abs(jac_sim)))
            try:
                if mean_jac_sim[feature_pair_high_cor_idx[0]] > mean_jac_sim[feature_pair_high_cor_idx[1]]:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[0]]] = 1
                else:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[1]]] = 1
            except:
                feature_pair_high_cor_idx = feature_pair_high_cor_idx[0]
                if mean_jac_sim[feature_pair_high_cor_idx[0]] > mean_jac_sim[feature_pair_high_cor_idx[1]]:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[0]]] = 1
                else:
                    features_excluded[X_train_NA_features_index_copy[feature_pair_high_cor_idx[1]]] = 1
        else:
            stopper = True

    X_train_cleaned = copy.deepcopy(X_train.loc[:, (features_excluded == 0)])
    X_test_cleaned = copy.deepcopy(X_test.loc[:, (features_excluded == 0)])
    features_index_copy = copy.deepcopy(X_train_NA_features_index[features_excluded == 0])

    return X_train_cleaned, X_test_cleaned, features_index_copy, features_excluded


def mice_mode_imputation(X_train, X_test, random_state_seed):
    """Missing Values are replaced with mode values for binary features and iterative MICE imputations for dimensional features"""
    # Binary features
    imp_mode = SimpleImputer(missing_values=777777, strategy='most_frequent')
    imp_mode.fit(X_train)
    X_train_imputed = imp_mode.transform(X_train)
    X_test_imputed = imp_mode.transform(X_test)

    ## Dimensional features: training set
    imp_arith_mice = IterativeImputer(estimator=BayesianRidge(), missing_values=999999,
                                      sample_posterior=True, max_iter=10, initial_strategy="mean", random_state=random_state_seed)
    imp_arith_mice.fit(X_train_imputed)
    X_train_imputed = imp_arith_mice.transform(X_train_imputed)
    X_test_imputed = imp_arith_mice.transform(X_test_imputed)


    return X_train_imputed, X_test_imputed


def z_scaling(X_train_imputed, X_test_imputed):
    """Dimensional features are rescaled using a standard Scaler"""
    scaler=ColumnTransformer([("standard", preprocessing.StandardScaler(copy=True, with_mean=True, with_std=True),
                               list(((np.sort(X_train_imputed,axis=0)[1:] != np.sort(X_train_imputed,axis=0)[:-1]).sum(axis=0)+1)>2))],
                               remainder='passthrough')
    X_train_imputed_scaled = scaler.fit_transform(X_train_imputed)
    X_test_imputed_scaled = scaler.transform(X_test_imputed)

    return X_train_imputed_scaled, X_test_imputed_scaled


def result_metrics(y_prediction):
    """Result metrics are calculated and collected in a dictionary"""
    results_metrics = {}
    ## Correlation
    correlation = np.corrcoef(y_prediction['y_pred_factual'],y_prediction['y_true'])[0,1]

    # Error
    mae = mean_absolute_error(y_prediction['y_true'],y_prediction['y_pred_factual'])
    rmse = math.sqrt(mean_squared_error(y_prediction['y_true'],y_prediction['y_pred_factual']))

    # PAI
    pai = np.zeros((len(y_prediction),1))
    pai = y_prediction['y_pred_factual'] - y_prediction['y_pred_counterfactual'] # y_pred_factual - y_pred_counterfactual: #positive Value: counterfactual predicted to be superior to factual, as lower severity scores are better
    abspai = abs(pai)

    # Observed outcome optimal / nonoptimal
    obs_outcomes_optimal = []
    obs_outcomes_nonoptimal = []

    for i_results in range(len(y_prediction)):
        if pai[i_results] < 0:
            obs_outcomes_optimal.append(y_prediction['y_true'][i_results])
        else:
            obs_outcomes_nonoptimal.append(y_prediction['y_true'][i_results])

    pai_index = np.array(list(range(pai.shape[0])))
    median = np.median(abs(pai))
    pai_50_percent = pai[abs(pai)>median]
    abspai_50_percent = abs(pai_50_percent)

    obs_outcomes_optimal_pai_50_percent = []
    obs_outcomes_nonoptimal_pai_50_percent = []

    for i_results in range(len(pai_index)):
        if pai[i_results] < 0:
            if abs(pai[i_results]) > median:
                obs_outcomes_optimal_pai_50_percent.append(y_prediction['y_true'][i_results])
        else:
            if abs(pai[i_results]) > median:
                obs_outcomes_nonoptimal_pai_50_percent.append(y_prediction['y_true'][i_results])

    results_metrics = {"correlation":correlation, "RMSE": rmse, "MAE": mae, "pai": pai,
                    "obs_outcomes_optimal": obs_outcomes_optimal, "obs_outcomes_nonoptimal": obs_outcomes_nonoptimal,
                    "pai_50_percent": pai_50_percent, "obs_outcomes_optimal_pai_50_percent": obs_outcomes_optimal_pai_50_percent,
                    "obs_outcomes_nonoptimal_pai_50_percent": obs_outcomes_nonoptimal_pai_50_percent,
                    "abspai":abspai, "abspai_50_percent": abspai_50_percent}

    return results_metrics


def aggregate_iterations():
    """The results of the single iterations are loaded, aggregated (means, max and min and std values) and saved."""
    global PATH_WORKINGDIRECTORY, OPTIONS_OVERALL

    varnames=list(('correlation_all_cv_sum_all','RMSE_all_cv_sum_all','MAE_all_cv_sum_all',
                   'pai_all_cv_sum_tx_alternative1','pai_all_cv_sum_tx_alternative0','pai_all_cv_sum_all',
                   'abspai_all_cv_sum_tx_alternative1','abspai_all_cv_sum_tx_alternative0','abspai_all_cv_sum_all',
                   'cohens_d_tx_alternative1','cohens_d_tx_alternative0','cohens_d_all',
                   'obs_outcomes_optimal_all_cv_sum_tx_alternative1', 'obs_outcomes_nonoptimal_all_cv_sum_tx_alternative1',
                   'obs_outcomes_optimal_all_cv_sum_tx_alternative0', 'obs_outcomes_nonoptimal_all_cv_sum_tx_alternative0',
                   'obs_outcomes_optimal_all_cv_sum_all', 'obs_outcomes_nonoptimal_all_cv_sum_all',
                   'pai_all_cv_sum_50_percent_tx_alternative1','pai_all_cv_sum_50_percent_tx_alternative0','pai_all_cv_sum_50_percent_all',
                   'abspai_all_cv_sum_50_percent_tx_alternative1','abspai_all_cv_sum_50_percent_tx_alternative0','abspai_all_cv_sum_50_percent_all',
                   'cohens_d_50_percent_tx_alternative1','cohens_d_50_percent_tx_alternative0','cohens_d_50_percent_all',
                   'obs_outcomes_optimal_all_cv_sum_50_percent_tx_alternative1','obs_outcomes_nonoptimal_all_cv_sum_50_percent_tx_alternative1',
                   'obs_outcomes_optimal_all_cv_sum_50_percent_tx_alternative0','obs_outcomes_nonoptimal_all_cv_sum_50_percent_tx_alternative0',
                   'obs_outcomes_optimal_all_cv_sum_50_percent_all','obs_outcomes_nonoptimal_all_cv_sum_50_percent_all'))

    # Load results and create dictionary
    results_dict_aggregate = {}
    for var_idx in range(0,len(varnames)):
        var_name = varnames[var_idx]
        # load results
        save_option = os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'individual_rounds',(OPTIONS_OVERALL['name_model'] + '_per_iteration_' + var_name + '.txt'))
        loaded_var = np.loadtxt(save_option, delimiter=",", unpack=False)
        # Create dictionary with needed values
        results_dict_aggregate[var_name] = {}
        if OPTIONS_OVERALL["number_iterations"] > 1:
            results_dict_aggregate[var_name]["Min"]= min(loaded_var)
            results_dict_aggregate[var_name]["Max"]= max(loaded_var)
            results_dict_aggregate[var_name]["Mean"]= np.mean(loaded_var)
            results_dict_aggregate[var_name]["Std"]= np.std(loaded_var)
        elif OPTIONS_OVERALL["number_iterations"] == 1:
            results_dict_aggregate[var_name]["Min"]= "NA"
            results_dict_aggregate[var_name]["Max"]= "NA"
            results_dict_aggregate[var_name]["Mean"]= loaded_var
            results_dict_aggregate[var_name]["Std"]= "NA"


    # Write results into file
    savepath_option = os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'accuracy',(OPTIONS_OVERALL['name_model'] + '.txt'))
    f = open(savepath_option, 'w')
    f.write('Model name: ' + str(OPTIONS_OVERALL['name_model']) +
            '\nThe number of iterations: ' + str(OPTIONS_OVERALL['number_iterations']) +
            '\nThe number of folds in k-fold: ' + str(OPTIONS_OVERALL['number_folds']) +
            '\nThe scikit-learn version is: ' + str(sklearn.__version__))

    def write_metrics(outcome, naming):
        f.write('\n')
        for key in results_dict_aggregate[outcome]:
            f.write ('\n'+ str(key) + ' ' + naming + ': '+ str(results_dict_aggregate[outcome][key]))

    f.write('\n\nCorrelation, MAE and RMSE values for across both groups in testset')
    write_metrics(outcome = "correlation_all_cv_sum_all", naming = "Correlation all")
    write_metrics(outcome = "RMSE_all_cv_sum_all", naming = "RMSE all")
    write_metrics(outcome = "MAE_all_cv_sum_all", naming = "MAE all")

    f.write('\n\nAbsolute scores for the PAI (abspai) in testset')
    write_metrics(outcome = "abspai_all_cv_sum_tx_alternative1", naming = "abspai tx_alternative1")
    write_metrics(outcome = "abspai_all_cv_sum_tx_alternative0", naming = "abspai tx_alternative0")
    write_metrics(outcome = "abspai_all_cv_sum_all", naming = "abspai all")

    f.write('\n\nNon-absolute scores for the PAI (abspai) in testset')
    write_metrics(outcome = "pai_all_cv_sum_tx_alternative1", naming = "pai tx_alternative1")
    write_metrics(outcome = "pai_all_cv_sum_tx_alternative0", naming = "pai tx_alternative0")
    write_metrics(outcome = "pai_all_cv_sum_all", naming = "pai all")

    f.write('\n\nMean observed outcome scores for treatment alternatives (tx_alternative), for patients where this was predicted as optimal and nonoptimal in testset')
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_tx_alternative1", naming = "mean_obs_outcomes_optimal tx_alternative1")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_tx_alternative1", naming = "mean_obs_outcomes_nonoptimal tx_alternative1")
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_tx_alternative0", naming = "mean_obs_outcomes_optimal tx_alternative0")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_tx_alternative0", naming = "mean_obs_outcomes_nonoptimal tx_alternative0")
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_all", naming = "mean_obs_outcomes_optimal all")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_all", naming = "mean_obs_outcomes_nonoptimal all")

    f.write('\n\nMean of Cohens D for these differences in testset')
    write_metrics(outcome = "cohens_d_tx_alternative1", naming = "Cohens D tx_alternative1")
    write_metrics(outcome = "cohens_d_tx_alternative0", naming = "Cohens D tx_alternative0")
    write_metrics(outcome = "cohens_d_all", naming = "Cohens D all")

    f.write('\n\nAbsolute scores for the PAI for the subsample with 50% largest PAIs (abspai_50_percent) in testset')
    write_metrics(outcome = "abspai_all_cv_sum_50_percent_tx_alternative1", naming = "abspai_50_percent tx_alternative1")
    write_metrics(outcome = "abspai_all_cv_sum_50_percent_tx_alternative0", naming = "abspai_50_percent tx_alternative0")
    write_metrics(outcome = "abspai_all_cv_sum_50_percent_all", naming = "abspai_50_percent all")

    f.write('\n\nNon-absolute scores for the PAI for the subsample with 50% largest PAIs in testset')
    write_metrics(outcome = "pai_all_cv_sum_50_percent_tx_alternative1", naming = "pai_50_percent tx_alternative1")
    write_metrics(outcome = "pai_all_cv_sum_50_percent_tx_alternative0", naming = "pai_50_percent tx_alternative0")
    write_metrics(outcome = "pai_all_cv_sum_50_percent_all", naming = "pai_50_percent all")

    f.write('\n\nMean observed outcome scores for treatment alternatives (tx_alternative), for patients where this was predicted as optimal and nonoptimal in testset, for the subsample with 50% largest PAIs')
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_50_percent_tx_alternative1", naming = "mean_obs_outcomes_optimal 50_percent_tx_alternative1")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_50_percent_tx_alternative1", naming = "mean_obs_outcomes_nonoptimal 50_percent_tx_alternative1")
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_50_percent_tx_alternative0", naming = "mean_obs_outcomes_optimal 50_percent_tx_alternative0")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_50_percent_tx_alternative0", naming = "mean_obs_outcomes_nonoptimal 50_percent_tx_alternative0")
    write_metrics(outcome = "obs_outcomes_optimal_all_cv_sum_50_percent_all", naming = "mean_obs_outcomes_optimal 50_percent all")
    write_metrics(outcome = "obs_outcomes_nonoptimal_all_cv_sum_50_percent_all", naming = "mean_obs_outcomes_nonoptimal 50_percent all")

    f.write('\n\nMean of Cohens D for these differences for the subsample with 50% largest PAIs in testset')
    write_metrics(outcome = "cohens_d_50_percent_tx_alternative1", naming = "Cohens D 50_percent_tx_alternative1")
    write_metrics(outcome = "cohens_d_50_percent_tx_alternative0", naming = "Cohens D 50_percent_tx_alternative0")
    write_metrics(outcome = "cohens_d_50_percent_all", naming = "Cohens D 50_percent_all")

    f.close()

    return results_dict_aggregate


def reminder():
    """Most important prerequisites to execute this code are printed."""
    print("Are data read-in as tab-separated text?")
    print("Have the values 777777, 999999 been assigned to NAs / missing?")
    print("Have you provided the paths to directories?"),
    print("Are binaries coded as 0.5, -0.5?")
    print("Is group membership coded as 0, 1?")
    input("Press Enter to continue...")



if __name__ == '__main__':
    reminder()
    create_folders()
    print('\nThe scikit-learn version is {}.'.format(sklearn.__version__))
    runs_list = []
    outcomes = []

    for i in range (OPTIONS_OVERALL['number_iterations']):
        runs_list.append(i)
    #pool = Pool(4)     #cluster
    #pool.map(do_iterations,runs_list)    #cluster
    #pool.close()   #cluster
    #pool.join()    #cluster
    outcomes[:] = map(do_iterations,runs_list)  #local computer
    results_dict = aggregate_iterations()

    elapsed_time = time.time() - start_time
    print('\nThe time for running was {}.'.format(elapsed_time))
    print('Results from all iterations combined were saved at {}.'.format(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'accuracy')))
    print('Results from all iterations individually were saved at {}.'.format(os.path.join(PATH_WORKINGDIRECTORY,OPTIONS_OVERALL['name_model'],'individual_rounds')))
