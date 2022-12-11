# PAI

The Personalized Advantage Index (PAI) was introduced first by deRubeis et al. (2014; see References) and is a well-used approach to predict which one of several available treatment alternatives is optimal for an individual patient. The PAI has seen many different implementations. Here, we provide a low-bias pipeline for use by the scientific community. 

# How to use this script

## Data preparation:
    
Define a working directory and set this under path_workingdirectory
    
Prepare the data: this script takes tab-delimited text files as input for features, labels and group membership (i.e. treatment arm). Usually, tab-delimited text can easily be exported from statistic programs or excel  
Make sure that the group membership file codes the groups as number, for instance 0 for CBT and 1 for SSRI  
Make sure that categorical variables are one-hot encoded as binaries, and these binaries are scaled to 0.5 and -0.5
    
Make sure the data in these text files uses a point as decimal separator and variable names do not include special characters  
The script assumes that all text files include the variable name in the top line  
Save the feature, label and group data in a subfolder 'data' under your working directory
    
Missing Values: this script uses MICE to impute missing for dimensional features and mode imputation for binary features. Consequently, missings must be differentially coded depending on type. Please code a missing dimensional value as 999999 and a missing binary value as 777777

    
## Script preparation:
Make sure all needed requirements for this script are installed by running "pip install -r "requirements.txt". 
Name your model in options_overall['name_model'] - this will be used to name all outputs by the script  
Set the number of total iterations under options_overall['number_iterations']  
Set the of folds for the k-fold under options_overall['number_folds']  
Give the names of your text files including features, labels and group membership under options_overall['name_features'], options_overall['name_labels'] , options_overall['name_groups_id']   
Use map or pool.map at the end of the script depending on whether you run this on your local computer or on a cluster  

# Empirical and theoretical foundations of design choices

There are plenty of different options for preparing the data and the machine learning pipeline. Mostly, no clear data is available suggesting which approches are superior to others. Still, there were some papers that we considered important when designing this pipeline, which are presented below:

Centering of variables and centering of binary variables to -0.5 and 0.5 -- Kraemer & Blasey (2004)  
Elastic net feature reduction -- Bennemann et al. (2022)  
Random Forest -- Grinsztajn et al (preprint)  
Refraining from LOO-CV and using a repeated 5-fold stratified train-test split -- Varoquaux (2018) & Varoquaux et al. (2017) & Flint et al. (2021) & the observation that prediction performance varies substantially between iterations in our own previous papers, including Leehr et al. (2021) & Hilbert et al. (2021)


# References

1. Bennemann et al. (2022). Predicting patients who will drop out of out-patient psychotherapy using machine learning algorithms. The British Journal of Psychiatry, 220, 192–201.
2. DeRubeis et al (2014). The Personalized Advantage Index: translating research on prediction into individualized treatment recommendations. A demonstration. PLOS One, 9(1), e83875.
3. Flint et al. (2021). Systematic misestimation of machine learning performance in neuroimaging studies of depression. Neuropsychopharmacology, 46, 1510–1517.
4. Grinsztajn et al (preprint). Why do tree-based models still outperform deep learning on tabular data? arXiv, 2207.08815.
5. Hilbert et al. (2021). Identifying CBT non-response among OCD outpatients: a machine-learning approach. Psychotherapy Research, 31(1), 52-62.
6. Kraemer & Blasey (2004). Centring in regression analyses: a strategy to prevent errors in statistical inference. International Journal of Methods in Psychiatric Research, 13(3), 141-51.
7. Leehr et al. (2021). Clinical predictors of treatment response towards exposure therapy in virtuo in spider phobia: a machine learning and external cross-validation approach. Journal of Anxiety Disorders, 83, 102448. 
8. Varoquaux (2018). Cross-validation failure: Small sample sizes lead to large error bars. NeuroImage, 180(A), 68-77.
9. Varoquaux et al. (2017). Assessing and tuning brain decoders: Cross-validation, caveats, and guidelines. NeuroImage, 145, 166–179.
