#!/usr/bin/env python

import pandas as pd
import numpy as np
import os, argparse as ap
import sys
import itertools as it
sys.path.append(os.path.join(os.path.dirname(sys.path[0]), "python_modules"))
from statsmodels.stats.multitest import fdrcorrection
from meta_analysis_runner import singleStudyEffect
from meta_analysis_runner import meta_analysis_with_linear_model
from meta_analysis_runner import analysis_with_linear_model
from meta_analyses import paule_mandel_tau
from meta_analyses import RE_meta_binary
from meta_analyses import RE_meta

def read_params():
    p = ap.ArgumentParser(description=\
        "", \
        formatter_class=ap.RawTextHelpFormatter)
    add = p.add_argument
    add("-nm", "--names", nargs="+", type=str, default=[], help=\
        "A series of strings, idenfitying the meta-analysis "
        "you are meta-analysing. E.g.: stagei stageii stageiii")
    add("-s", "--sheets", nargs="+", type=str, default=[], help=\
        "A series of tabular results. E.g.: stagei.csv stageii.csv stageiii.csv")
    add("-es", "--effect_size", type=str, nargs="+", default="CohenD", help=\
        "A list containing the name/s of the column storing the effect size "
        "in the different meta-analysis sheets. Must be: either long 1, or as "
        "long as the the number of meta-analysis.")
    add("-se", "--std_error", type=str, nargs="+", default="SE", help=\
        "A list storing the name of Std.Err columns of the meta-analyses. "
        "Either long 1 or len([meta-analyses])")
    add("-qs", "--qvals", type=str, nargs="+", default="Qvalue", help=\
        "Stores the column(s)-name of the corrected P-values of each [meta-]analysis")
    add("-ps", "--pvals", type=str, nargs="+", default=[""], help=\
        "Optional: column(s) of the raw-Pvalues of each analysis")
    add("-pe", "--prevalence", type=str, nargs="+", default=[""], help=\
        "A list either 1-long or as long as the n. of analyses. "
        "If correctly specified, uses the column prevalence to filter out "
        "results based on the next argument. Default=[unactive]")
    add("-mp", "--min_prevalence", type=float, default=0.01, help=\
        "If the --prevalence arg is activated, uses this cutoff to filter "
        "meta-analyses results.")
    add("-ms", "--min_studies", type=int, default=4, help=\
        "Minimum number of meta-analysis in which a feature must be present "
        "with a real effect-size to be considerable for the hierarchical meta-analysis.")
    add("-n", "--n_studies", type=str, nargs="+", default=[""], help=\
        "Either 1-long or as long as the len(names). Stores the name of the "
        "columns with the total n of samples in the meta-analysis. "
        "NOTE that this parameter is necessary only in the meta-correlation analysis, SEE after.")
    add("-k", "--kind", type=str, choices=["mc", "re"], default="re", help=\
        "The kind of analysis: re (random-effect) or mc (meta-correlation). "
        "Specify the second if this is a meta-correlation analysis reather than "
        "a standardised-mean-difference-based one. NOTE: If kind = mc you have to specify the --n_studies param "
        "(meta-correlation needs the total N of each study)")
    add("-H", "--heterogeneity", type=str, default="PM", choices=["DL", "PM", "FIX"], help=\
        "There are 2 heterogeeity implemented, PM and DL, and an optional FIX for the "
        "fixed effect model.")
    add("-v", "--var", action="store_true", help="Activating this flag, SE column is treated as the variance directly.")
    add("-o", "--outfile", type=str, default="")
    
    print(vars(p.parse_args()))
    return p.parse_args()


def parse_args(args):
    names = args.names
    analyses = args.sheets
    panda = lambda e : pd.read_csv(e, sep="\t", header=0, index_col=0, low_memory=False, engine="c")
    esizes = args.effect_size
    stderrs = args.std_error
    qvals = args.qvals
    pvals = args.pvals
    prevalence = args.prevalence
    n_studies = args.n_studies

    if (not names) or (not analyses):
        raise ValueError("One of Names or Analyses are empty. Must both containg their argument, exiting")
    if (len(names)!=len(analyses)):
        raise IndexError("The lenght of your analyses-name don't match the lenght of the analyses list, aborting")
    if (len(esizes)>1) and (len(esizes)!=len(names)):
        raise IndexError("The len of the effect size column is different from 1 AND from the number of analysis queried. Exiting")
    if (len(stderrs)>1) and (len(stderrs)!=len(names)):
        raise IndexError("The len of the std.err column is different from 1 AND from the number of analysis queried. Exiting")
    if (len(qvals)>1) and (len(qvals)!=len(names)):
        raise IndexError("The len of the qvals column is different from 1 AND from the number of analysis queried. Exiting")

    if pvals[0] and (len(pvals)>1) and (len(pvals)!=len(names)):
        raise IndexError("The len of pvalue is not null, 1 or as long as names.")

    if prevalence[0] and (len(prevalence)>1) and (len(prevalence)!=len(names)):
        raise SyntaxError("The len of the prevalence column is different from 1 AND from the number of analysis queried AND from \"\". "
            "Unactivate this flag (default) to exclude the filter by prevalence. Exiting")
    if (args.kind.upper()=="MC") and (not n_studies):
        raise SyntaxError("You asked a MetaCorrelation kind, but no --n_studies flag for the columns to parse for the "
            "n-of-the-studies was specified.")
    if (args.kind.upper()=="MC") and (len(n_studies)>1) and (len( n_studies )!=len(names)):
        raise ValueError("The len of the n_studies column is different from 1 AND from the number of analysis queried, "
            "and a MC analysis is asked. Specify correctly the n_studies paramater.")

    hier = {\
        "NAMES": names,
        "ANALYSES": [panda(s) for s in analyses],
        "ESIZE-COL": esizes if len(esizes)>1 else esizes*len(names),
        "SE-COL": stderrs if len(stderrs)>1 else stderrs*len(names),
        "P-COL": pvals if len(pvals)>1 else pvals*len(names),
        "Q-COL": qvals if len(qvals)>1 else qvals*len(names),
        "PREV-COL": prevalence if len(prevalence)>1 else prevalence*len(names), 
        "N-STUDIES": n_studies if len(n_studies)>1 else n_studies*len(names),
        "MIN-P": args.min_prevalence, 
        "MIN-STUDIES": args.min_studies,
        "TYPE": args.kind.upper(), 
        "H": args.heterogeneity,
	"Var": args.var
        }

    print(hier)
    return hier




def hierarchical_analysis(args, a_certain_response): ## le pravelcen le possiamo filtrare prima

    N = len(args["NAMES"])
    get = lambda frame, response, column : frame.loc[ response, column ] if (response in frame.index) else np.nan
    


    if args["TYPE"] == "RE":
     
        Effects = [ get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) ) ]

        Nms = [ args["NAMES"][i] for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) )]
 
        Qvls = [ get( args["ANALYSES"][i], a_certain_response, args["Q-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["Q-COL"][i] ) ) ]

        Pvls = [ get( args["ANALYSES"][i], a_certain_response, args["P-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["P-COL"][i] ) ) ]

        SEs = [ get( args["ANALYSES"][i], a_certain_response, args["SE-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["SE-COL"][i] ) ) ]

        if len(Effects)>=args["MIN-STUDIES"]:
            Variances = [ get( args["ANALYSES"][i], a_certain_response, args["SE-COL"][i] )**\
	        (2. if (not args["Var"]) else 1.) for i in range(N) if \
                np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) ) ]
 
            re = RE_meta_binary( Effects, Pvls, Nms, [None]*len(Effects), [None]*len(Effects), \
		a_certain_response, EFF="precomputed", variances_from_outside=Variances, CI=False, HET=args["H"]  )

            for nm,qv,se in zip(Nms, Qvls, SEs):
                re.result[nm + "_Qvalue"] = qv
                re.result[nm + "_SE_RE"] = se

            sys.stdout.write("%s (%i associtaions found) Random Effect = %.3f [H: %.3f %.3f  %.3f]   (  %.4f  )\n" \
                %( a_certain_response, len(Nms), re.RE, re.t2_DL, re.t2_PM, re.I2, re.Pval) )

            return re.result

        else:
            return np.nan



    elif args["TYPE"] == "MC":

        Effects = [ get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) ) ]
 
        Nms = [ args["NAMES"][i] for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) )]

        Nns = [args["ANALYSES"][i][args["N-STUDIES"][i]] for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["ESIZE-COL"][i] ) )]

        Qvls = [ get( args["ANALYSES"][i], a_certain_response, args["Q-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["Q-COL"][i] ) ) ]

        Pvls = [ get( args["ANALYSES"][i], a_certain_response, args["P-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["P-COL"][i] ) ) ]

        SEs = [ get( args["ANALYSES"][i], a_certain_response, args["SE-COL"][i] ) for i in range(N) if \
            np.isfinite( get( args["ANALYSES"][i], a_certain_response, args["SE-COL"][i] ) ) ]

        if len(Effects)>=args["MIN-STUDIES"]:
            re = RE_meta( Effects, Pvls, Nms, Nns, a_certain_response, het=args["H"], REG=True )
   
            for nm,qv,se in zip(Nms, Qvls, SEs):
                re.result[nm + "_Qvalue"] = qv
                re.result[nm + "_SE_RE"] = se
                        
            sys.stdout.write("%s (%i associtaions found) Random Effect = %.3f [H: %.3f %.3f  %.3f]   (  %.4f  )\n" \
                %( a_certain_response, len(Nms), re.RE, re.t2_DL, re.t2_PM, re.I2, re.Pval) )

            return re.result

        else:
            return np.nan




def main():
    params = read_params()

    if not params.outfile:
        raise SyntaxError("Please, specify an --outfile and retry. Exiting")

    hier_args = parse_args(params)
    meta_of_meta = []

    ## qui definisci le feature
    Features = set( list( it.chain.from_iterable(  [ a.index.tolist() for a in hier_args["ANALYSES"]  ]  ) ) )

    ## qui filtei per pravelcne
    
    for response in Features:
 
            if not params.prevalence[0]:
                mean_prevalence = 1.0
            else:
                mean_prevalence = np.mean( [  a.loc[ response, hier_args["PREV-COL"][e] ] for e,a in \
                    enumerate(hier_args["ANALYSES"])  if (response in a.index) ] )

            if mean_prevalence >= hier_args["MIN-P"]:
 
                res = hierarchical_analysis(hier_args, response)

                if params.prevalence[0]:
                    setattr(res, "mean-prevalence", mean_prevalence)
                
                if isinstance(res, pd.core.frame.DataFrame):
                    if len(meta_of_meta) == 0.:
                        meta_of_meta = res
                    else:
                        meta_of_meta = meta_of_meta.append(res)
                    

    if isinstance(meta_of_meta, list):
        raise ValueError("No feats meet youre reqeuirementes... Check manually if these meta-analyses have something in common "
            "or relax the min_prevalence and the min-studies argument.")

    _, fdr = fdrcorrection( np.nan_to_num(meta_of_meta["RE_Pvalue"].values.astype(float), nan=1.0), alpha=0.05)
    
    meta_of_meta.insert((len( hier_args["NAMES"] )*2)+2, "RE_Qvalue", fdr)

    ## sort
    meta_of_meta[ "Q" ] = [ (0 if q<0.2 else 1) for q in meta_of_meta["RE_Qvalue"].values ]
    meta_of_meta[ "E" ] = np.abs( meta_of_meta["RE_Effect"].values  )
    meta_of_meta.sort_values(by=[ "Q", "E" ], ascending=[True, False], inplace=True)
    del meta_of_meta[ "Q" ]
    del meta_of_meta[ "E" ]

    meta_of_meta.fillna("NA", inplace=True)
    meta_of_meta.to_csv(params.outfile, sep="\t", header=True, index=True)


if __name__ == "__main__":
    main()
