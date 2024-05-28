#%%

import scanpy as sc
import decoupler as dc

# Only needed for processing https://decoupler-py.readthedocs.io/en/latest/notebooks/bulk.html
import numpy as np
import pandas as pd
from anndata import AnnData
import os

#%%


# Retrieve CollecTRI gene regulatory network
collectri = dc.get_collectri(organism='human', split_complexes=False)
# Read raw data and process it
file_path = '/Users/charliebarker/Desktop/Melanoma_Resistance/data/RNAseq/data/geneCounts_fixed.csv'
design_path = '/Users/charliebarker/Desktop/Melanoma_Resistance/data/RNAseq/Study_design.csv'

adata = pd.read_csv(file_path)
design = pd.read_csv(design_path)
column_mapping = dict(zip(adata.columns[1:], design.set_index('Study_ID')['New_Sample_name']))
adata.rename(columns=column_mapping, inplace=True)

#%%

# Retrieve gene symbols
annot = sc.queries.biomart_annotations("hsapiens",
        ["ensembl_gene_id", "external_gene_name"],
        use_cache=False
    ).set_index("ensembl_gene_id")

# Filter genes not in annotation
adata.set_index('ENSEMBL_ID', inplace=True)
adata = adata[adata.index.isin(annot.index)]
# Assign gene symbols
adata['gene_symbol'] = [annot.loc[ensembl_id,'external_gene_name'] for ensembl_id in adata.index]
adata = adata.reset_index().rename(columns={'index': 'ensembl_gene_id'}).set_index('gene_symbol')

# Remove rows with all zero values (empty rows)
adata = adata[(adata != 0).any(axis=1)]

# Rename columns with underscores to replace with spaces
adata.columns = adata.columns.str.replace('__', ' ')

# Remove the 'ENSEMBL_ID' column
adata = adata.drop(columns='ENSEMBL_ID')

# Transform to AnnData object
adata = adata.T
# Remove columns with NaN column names
adata = adata.loc[:, ~adata.columns.isna()]

adata = AnnData(adata, dtype=np.float32)
adata.var_names_make_unique()
#%%

#Inside an AnnData object, there is the .obs attribute where we can store the metadata of our samples.

# Process treatment information
adata.obs['sample-name'] = adata.obs.index.tolist()
adata.obs['trametinib'] = ['treatment' if 'Trametinib' in sample_id else 'control' for sample_id in adata.obs.index]
adata.obs['vemurafenib'] = ['treatment' if 'Vermurafenib' in sample_id else 'control' for sample_id in adata.obs.index]
adata.obs['combination'] = ['treatment' if 'and' in sample_id else 'control' for sample_id in adata.obs.index]
adata.obs['ARID1A_KO'] = ['treatment' if 'ARID1A_KO' in sample_id else 'control' for sample_id in adata.obs.index]

#%%
#Filter genes by expression

# Visualize metadata

min_count = 5
min_total_count = 10


dc.plot_filter_by_expr(adata, group=None, min_count=min_count, min_total_count=min_total_count, large_n=1, min_prop=.4)

# Obtain genes that pass the thresholds
genes = dc.filter_by_expr(adata, group=None, min_count=min_count, min_total_count=min_total_count, large_n=1, min_prop=.4)


#%%
#Run DESEQ2

# Filter by these genes
adata = adata[:, genes].copy()

# Import DESeq2
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

# Build DESeq2 object
dds = DeseqDataSet(
    adata=adata,
    design_factors='sample-name',
    ref_level = ['sample-name', 'Untreated WT'],
    refit_cooks=True,
    n_cpus=8,
)
# Compute LFCs
dds.deseq2()

#%%
# Extract contrast

stat_res = DeseqStats(dds, contrast=["sample-name", 'Untreated ARID1A-KO', 'Untreated WT'], 
                      n_cpus=8)


exp_name = 'sample-name Untreated ARID1A-KO vs Untreated WT'
# Compute Wald test
stat_res.summary()

# Shrink LFCs
stat_res.lfc_shrink()

# Extract results
results_df = stat_res.results_df
results_df.to_csv('/Users/charliebarker/Desktop/Melanoma_Resistance/results/transcriptomics/arid1a_lfc.csv')

dc.plot_volcano_df(results_df, x='log2FoldChange', y='padj', top=20)

#%%
#transcription factor inference 

# Retrieve CollecTRI gene regulatory network
mat = results_df[['stat']].T.rename(index={'stat': exp_name})


tf_acts, tf_pvals = dc.run_ulm(mat=mat, net=collectri, verbose=True)	\

# Extract logFCs and pvals
logFCs = results_df[['log2FoldChange']].T.rename(index={'log2FoldChange': exp_name})
pvals = results_df[['padj']].T.rename(index={'padj': exp_name})
dc.plot_barplot(tf_acts, exp_name, top=25, vertical=True)
# Write tf_acts to a CSV file
tf_acts.T.to_csv('/Users/charliebarker/Desktop/Melanoma_Resistance/results/transcriptomics/tf_activity/arid1a_tf_acts.csv')
tf_pvals.T.to_csv('/Users/charliebarker/Desktop/Melanoma_Resistance/results/transcriptomics/tf_activity/arid1a_tf_pval.csv')

# %%
# Plot the specific targets

dc.plot_targets(results_df, stat='stat', source_name='RFX5', net=collectri, top=20)
dc.plot_targets(results_df, stat='stat', source_name='RFXAP', net=collectri, top=20)
dc.plot_targets(results_df, stat='stat', source_name='CIITA', net=collectri, top=20)
dc.plot_targets(results_df, stat='stat', source_name='TWIST1', net=collectri, top=20)

