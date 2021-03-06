import numpy as np
import soap
from .math import zscore
import scipy.stats
import json

class PyFGraph(object):
    def __init__(self, fgraph):
        self.fgraph_ = fgraph
        self.fnodes = []
        self.fnode_map = {}
        self.generations = None
        self.root_nodes = None
        self.map_generations = None
        self.extract()
        self.rank()
    def extract(self):
        self.fnodes = [ PyFNode(_) for _ in self.fgraph_ ]
        self.root_nodes = filter(lambda f: f.is_root, self.fnodes)
        self.map_generations = {}
        self.generations = sorted(list(set([ f.generation for f in self.fnodes ])))
        self.map_generations = { g: [] for g in self.generations }
        for f in self.fnodes:
            self.map_generations[f.generation].append(f)
        print "FGraph of size %d" % len(self.fnodes)
        for g in self.generations:
            print "  %4d nodes at generation %d" % (
                len(self.map_generations[g]), g)
        self.fnode_map = { f.expr: f for f in self.fnodes }
        for f in self.fnodes: f.resolveParents(self.fnode_map)
        return
    def rank(self, cumulative=False, ordinal=False, key=lambda f: np.abs(f.cov*f.confidence)):
        scores = [ key(f) for f in self.fnodes ]
        scores_cum = np.cumsum(sorted(scores))
        ranked = sorted(self.fnodes, key=key)
        for idx, r in enumerate(ranked):
            if ordinal:
                r.rank = float(idx)/(len(ranked)-1.)
            elif cumulative == True:
                r.rank = scores_cum[idx]/scores_cum[-1]*key(r)
            else:
                r.rank = key(r)
        return

class PyFGraphStats(object):
    def __init__(self, tags, covs, exs, q_values, q_values_nth, null_exs, null_covs, cov_tail_scaling_fct):
        self.n_samples = null_exs.shape[0]
        self.n_channels = null_exs.shape[1]
        self.tags = tags
        self.covs = covs
        self.exs = exs
        self.q_values = np.array(q_values)
        self.q_values_nth = np.array(q_values_nth)
        self.null_exs = null_exs # matrix of size SxC (samples by channels)
        self.null_covs = null_covs # matrix of size SxC
        self.cov_tail_scaling_fct = cov_tail_scaling_fct
        self.order = np.argsort(-np.abs(self.covs))
        self.evaluateTopNode()
    def evaluateTopNode(self):
        self.top_idx = self.order[0]
        self.top_tag = self.tags[self.top_idx]
        self.top_cov = self.covs[self.top_idx]
        self.top_q = self.q_values[self.top_idx]
        self.top_exceedence = self.exs[self.top_idx]
        self.top_avg_null_exceedence = np.average(self.null_exs[:,0])
        self.top_rho_harm = np.abs(self.top_cov)/(1.+self.top_exceedence)
        self.top_avg_null_cov = self.top_cov*(1.+self.top_avg_null_exceedence)/(1.+self.top_exceedence)
        self.percentiles = np.arange(0,110,10)
        self.top_avg_null_exc_percentiles = [ np.percentile(self.null_exs[:,0], p) for p in self.percentiles ]
        self.top_avg_null_cov_percentiles = [ self.top_cov*(1.+e)/(1.+self.top_exceedence) for e in self.top_avg_null_exc_percentiles ]
        return
    def calculateCovExceedencePercentiles(self, pctiles=None, log=None):
        if pctiles is None: pctiles = np.arange(0,110,10)
        covx_1st_list = []
        covx_nth_list = []
        for r in range(self.n_channels):
            covx_1st = self.calculateExpectedCovExceedenceRank(rank=r, rank_null=0, pctiles=pctiles)
            covx_nth = self.calculateExpectedCovExceedenceRank(rank=r, rank_null=r, pctiles=pctiles)
            covx_1st_list.append(covx_1st)
            covx_nth_list.append(covx_nth)
        covx_1st = np.array(covx_1st_list).T
        covx_nth = np.array(covx_nth_list).T
        return self.order, pctiles, covx_1st, covx_nth
    def calculateExpectedCovExceedenceRank(self, rank, rank_null, pctiles):
        idx = self.order[rank]
        cov = np.abs(self.covs[idx])
        exc = self.exs[idx]
        null_exceedence_pctiles = np.array([ np.percentile(self.null_exs[:,rank_null], p) for p in pctiles ])
        rho_harm = cov/(1.+exc) # harmonic tail cov for this channel
        null_cov_pctiles = cov*(1.+null_exceedence_pctiles)/(1.+exc)
        return -null_cov_pctiles+cov
    def summarize(self, log):
        log << "Top-ranked node: '%s'" % (self.top_tag) << log.endl
        log << "  [phys]   cov  = %+1.4f     exc  = %+1.4f     q = %1.4f" % (self.top_cov, self.top_exceedence, self.top_q) << log.endl
        log << "  [null]  <cov> = %+1.4f    <exc> = %+1.4f" % (self.top_avg_null_cov, self.top_avg_null_exceedence) << log.endl
        log << "Percentiles"
        for idx, p in enumerate(self.percentiles):
            log << "  [null] p = %1.2f  <cov>_p = %+1.4f  <exc>_p = %+1.4f" % (
                0.01*p, self.top_avg_null_cov_percentiles[idx], self.top_avg_null_exc_percentiles[idx]) << log.endl
        cidx = np.argmax(np.abs(self.covs))
        eidx = np.argmax(self.exs)
        qidx = np.argmax(self.q_values)
        log << "Max cov observed: c=%+1.4f @ %s" % (self.covs[cidx], self.tags[cidx]) << log.endl
        log << "Max exc observed: e=%+1.4f @ %s" % (self.exs[eidx], self.tags[eidx]) << log.endl
        log << "Max prb observed: q=%+1.4f @ %s" % (self.q_values[qidx], self.tags[qidx]) << log.endl
        return
    def tabulateExceedence(self, outfile):
        percentiles = np.arange(0, 110, 10)
        null_exs_percentiles = []
        for p in percentiles:
            null_exs_percentiles.append(np.percentile(self.null_exs, p, axis=0))
        null_exs_percentiles = np.array(null_exs_percentiles).T
        ranks = np.arange(len(self.exs))+1.
        ranks = ranks/ranks[-1]
        ofs = open(outfile, 'w')
        ofs.write('# rank exs null@' + ' null@'.join(map(str, percentiles)) + '\n')
        chunk = np.concatenate([ ranks.reshape((-1,1)), np.sort(self.exs)[::-1].reshape((-1,1)), null_exs_percentiles ], axis=1)
        np.savetxt(ofs, chunk)
        ofs.close()
        return
    def getChannelNullCovDist(self, channel_idx, ofs=None):
        dist = np.array([ 1.-np.arange(self.n_samples)/float(self.n_samples), self.null_covs[:,channel_idx]]).T
        if ofs: np.savetxt(ofs, dist)
        return dist

class PyFNode(object):
    def __init__(self, fnode):
        self.fnode_ = fnode
        self.parents_ = self.fnode_.getParents()
        self.parents = []
        self.is_root = fnode.is_root
        self.generation = fnode.generation
        self.expr = fnode.expr
        self.cov = fnode.cov
        self.confidence = fnode.q
        self.rank = -1
    def resolveParents(self, fnode_map):
        self.parents = [ fnode_map[p.expr] for p in self.parents_ ]

class CovTailScalingFct(object):
    def __init__(self, null_covs, tail_fraction):
        # <null_covs>: matrix SxC (#samples x #channels)
        from scipy.optimize import curve_fit
        def scaling_fct(x, a): return x**a
        p0_covs = np.percentile(null_covs, 100*(1.-2.0*tail_fraction), axis=0)
        p1_covs = np.percentile(null_covs, 100*(1.-1.0*tail_fraction), axis=0)
        #popt1, pcov1 = curve_fit(scaling_fct, p2_covs, p1_covs)
        #popt3, pcov3 = curve_fit(scaling_fct, p2_covs, p3_covs)
        self.tail_weight = (1.-p0_covs)/(1.-p1_covs)
    def __call__(self, x):
        return 1. #self.tail_weight

def calculate_exceedence(covs_harm, covs_sample, epsilon=1e-10, scale_fct=lambda c: c):
    # C = # channels
    # covs_harm: vec of length C
    # covs_sample: vec of length C
    # exs: vec of length C
    exs = (covs_sample-covs_harm)/(covs_harm)
    exs = exs*scale_fct(covs_sample)
    return exs

def generate_graph(
        features_with_props,
        uop_list,
        bop_list,
        unit_min_exp,
        unit_max_exp,
        correlation_measure,
        rank_coeff=0.25):
    assert len(uop_list) == len(bop_list)
    fgraph_options = soap.Options()
    fgraph_options.set("unit_min_exp", unit_min_exp)
    fgraph_options.set("unit_max_exp", unit_max_exp)
    fgraph_options.set("correlation_measure", correlation_measure)
    fgraph_options.set("rank_coeff", rank_coeff) # used if correlation_measure == 'mixed'
    fgraph = soap.FGraph(fgraph_options)
    for f in features_with_props:
        fgraph.addRootNode(str(f[0]), str(f[1]), str(f[2]), f[3], str(f[4]))
    for lidx in range(len(uop_list)):
        fgraph.addLayer(uop_list[lidx], bop_list[lidx])
    fgraph.generate()
    return fgraph

def fgraph_apply_batch(
        fgraph,
        IX_list,
        Y,
        log):
    if len(IX_list) > 0:
        npfga_dtype = IX_list[0].dtype
        covs = np.zeros((len(IX_list), len(fgraph)), dtype=npfga_dtype)
        Y = Y.reshape((-1,1))
        for i, IX in enumerate(IX_list):
            log << log.back << "Randomized control, instance" << i << log.flush
            covs[i,:] = fgraph.applyAndCorrelate(IX, Y, str(npfga_dtype))[:,0]
        log << log.endl
    else:
        covs = []
    return covs

def calculate_null_distribution(
        rand_covs,
        options,
        log,
        file_out=False):
    npfga_dtype = rand_covs.dtype
    # Dimensions and threshold
    n_channels = rand_covs.shape[1]
    n_samples = rand_covs.shape[0]
    p_threshold = 1. - options.tail_fraction
    i_threshold = int(p_threshold*n_samples+0.5)
    if log: log << "Tail contains %d samples" % (n_samples-i_threshold) << log.endl
    # Random-sampling convariance matrix
    # Rows -> sampling instances
    # Cols -> feature channels
    rand_cov_mat = np.copy(rand_covs)
    rand_cov_mat = np.abs(rand_cov_mat)
    # Sort covariance observations for each channel
    rand_covs = np.abs(rand_covs)
    rand_covs = np.sort(rand_covs, axis=0)
    # Fit scaling function
    cov_scaling_fct = CovTailScalingFct(rand_covs, options.tail_fraction)
    # Cumulative distribution for each channel
    rand_cum = np.ones((n_samples,1), dtype=npfga_dtype)
    rand_cum = np.cumsum(rand_cum, axis=0)
    rand_cum = (rand_cum-0.5) / rand_cum[-1,0]
    rand_cum = rand_cum[::-1,:]
    if file_out: np.savetxt('out_sis_channel_cov.hist', np.concatenate((rand_cum, rand_covs), axis=1))
    # Establish threshold for each channel
    thresholds = rand_covs[-int((1.-p_threshold)*n_samples),:]
    thresholds[np.where(thresholds < 1e-2)] = 1e-2
    t_min = np.min(thresholds)
    t_max = np.max(thresholds)
    t_std = np.std(thresholds)
    t_avg = np.average(thresholds)
    if log: log << "Channel-dependent thresholds: min avg max +/- std = %1.2f %1.2f %1.2f +/- %1.4f" % (
        t_min, t_avg, t_max, t_std) << log.endl
    # Peaks over threshold: calculate excesses for random samples
    if log: log << "Calculating excess for random samples" << log.endl
    pots = rand_covs[i_threshold:n_samples,:]
    pots = pots.shape[0]/np.sum(1./(pots+1e-10), axis=0) # harmonic average
    rand_exs_mat = np.zeros((n_samples,n_channels), dtype=npfga_dtype)
    for s in range(n_samples):
        if log: log << log.back << "- Sample %d/%d" % (s+1, n_samples) << log.flush
        rand_cov_sample = rand_cov_mat[s]
        exs = calculate_exceedence(pots, rand_cov_sample, scale_fct=cov_scaling_fct)
        #exs = -np.average((pots+1e-10-rand_cov_sample)/(pots+1e-10), axis=0)
        rand_exs_mat[s,:] = exs
    # Random excess distributions
    rand_exs = np.sort(rand_exs_mat, axis=1) # n_samples x n_channels
    rand_exs_cum = np.ones((n_channels,1), dtype=npfga_dtype) # n_channels x 1
    rand_exs_cum = np.cumsum(rand_exs_cum, axis=0)
    rand_exs_cum = (rand_exs_cum-0.5) / rand_exs_cum[-1,0]
    rand_exs_cum = rand_exs_cum[::-1,:]
    rand_exs_avg = np.average(rand_exs, axis=0)
    rand_exs_std = np.std(rand_exs, axis=0)
    # Rank distributions: covariance
    rand_covs_rank = np.sort(rand_cov_mat, axis=1)
    rand_covs_rank = np.sort(rand_covs_rank, axis=0)
    rand_covs_rank = rand_covs_rank[:,::-1]
    # Rank distributions: exceedence
    rand_exs_rank = np.sort(rand_exs, axis=0) # n_samples x n_channels
    rand_exs_rank = rand_exs_rank[:,::-1]
    rand_exs_rank_cum = np.ones((n_samples,1), dtype=npfga_dtype) # n_samples x 1
    rand_exs_rank_cum = np.cumsum(rand_exs_rank_cum, axis=0)
    rand_exs_rank_cum = (rand_exs_rank_cum-0.5) / rand_exs_rank_cum[-1,0]
    rand_exs_rank_cum = rand_exs_rank_cum[::-1,:]
    if file_out: np.savetxt('out_exs_rank_rand.txt', np.concatenate([ rand_exs_rank_cum, rand_exs_rank ], axis=1))
    # ... Histogram
    if file_out: np.savetxt('out_exs_rand.txt', np.array([rand_exs_cum[:,0], rand_exs_avg, rand_exs_std]).T)
    if log: log << log.endl
    return pots, rand_exs_cum, rand_exs_rank_cum, rand_exs_rank, rand_covs_rank, rand_covs, cov_scaling_fct

def rank_ptest(
        tags,
        covs,
        exs,
        exs_cum,
        rand_exs_rank,
        rand_exs_rank_cum,
        file_out=False):
    n_channels = exs.shape[0]
    idcs_sorted = np.argsort(exs)[::-1]
    p_first_list = np.zeros((n_channels,))
    p_rank_list = np.zeros((n_channels,))
    for rank, c in enumerate(idcs_sorted):
        # Calculate probability to observe feature given its rank
        ii = np.searchsorted(rand_exs_rank[:,rank], exs[c])
        if ii >= rand_exs_rank_cum.shape[0]:
            p0 = rand_exs_rank_cum[ii-1,0]
            p1 = 0.0
        elif ii <= 0:
            p0 = 1.0
            p1 = rand_exs_rank_cum[ii,0]
        else:
            p0 = rand_exs_rank_cum[ii-1,0]
            p1 = rand_exs_rank_cum[ii,0]
        p_rank = 0.5*(p0+p1)
        # Calculate probability to observe feature as highest-ranked
        ii = np.searchsorted(rand_exs_rank[:,0], exs[c])
        if ii >= rand_exs_rank_cum.shape[0]:
            p0 = rand_exs_rank_cum[ii-1,0]
            p1 = 0.0
        elif ii <= 0:
            p0 = 1.0
            p1 = rand_exs_rank_cum[ii,0]
        else:
            p0 = rand_exs_rank_cum[ii-1,0]
            p1 = rand_exs_rank_cum[ii,0]
        p_first = 0.5*(p0+p1)
        p_first_list[c] = p_first
        p_rank_list[c] = p_rank
    if file_out:
        np.savetxt('out_exs_phys.txt', np.array([
            exs_cum[::-1,0],
            exs[idcs_sorted],
            p_rank_list[idcs_sorted],
            p_first_list[idcs_sorted]]).T)
    q_values = [ 1.-p_first_list[c] for c in range(n_channels) ]
    q_values_nth = [ 1.-p_rank_list[c] for c in range(n_channels) ]
    return q_values, q_values_nth

def resample_IX_Y(IX, Y, n):
    for i in range(n):
        idcs = np.random.randint(0, IX.shape[0], size=(IX.shape[0],))
        yield i, IX[idcs], Y[idcs]
    return

def mode_resample_IX_Y(IX, Y, n, threshold):
    idcs0 = np.where(Y < threshold)[0]
    idcs1 = np.where(Y >= threshold)[0]
    n0 = len(idcs0)
    n1 = len(idcs1)
    for i in range(n):
        re_idcs0 = idcs0[np.random.randint(0, n0, size=(n0,))]
        re_idcs1 = idcs1[np.random.randint(0, n1, size=(n1,))]
        idcs = list(re_idcs0) + list(re_idcs1)
        yield i, IX[idcs], Y[idcs]
    return

def resample_range(start, end, n):
    for i in range(n):
        idcs = np.random.randint(start, end, size=(end-start,))
        yield i, idcs
    return

def calculate_fnode_complexities(fgraph, op_complexity_map):
    root_dependencies = {}
    for fnode in fgraph:
        parents = fnode.getParents()
        c = op_complexity_map[fnode.op_tag] + sum([ f.q for f in parents ])
        fnode.q = c
        if fnode.is_root: 
            root_dependencies[fnode.expr] = { "cplx": fnode.q, "deps": { fnode.expr } }
        else:
            deps = set()
            for p in parents:
                deps = deps.union(root_dependencies[p.expr]["deps"])
            root_dependencies[fnode.expr] = { "cplx": fnode.q, "deps": deps }
    cplxs = [ f.q for f in fgraph ]
    return np.array(cplxs), sorted(set(cplxs))

def calculate_null_and_test(tags, covs, rand_covs, options, log, with_stats):
    pots_1xC, ranks_Cx1, ranks_Sx1, null_exs_SxC, null_order_covs_SxC, null_covs_SxC, cov_scaling_fct = calculate_null_distribution(
        rand_covs,
        options=options,
        log=log)
    # Test statistic: abs(cov)
    covs_abs = np.abs(covs)
    cq_values, cq_values_nth = soap.soapy.npfga.rank_ptest(
        tags=tags,
        covs=covs_abs,
        exs=covs_abs,
        exs_cum=ranks_Cx1,
        rand_exs_rank=null_order_covs_SxC,
        rand_exs_rank_cum=ranks_Sx1)
    # Test statistic: exs(cov)
    exs = calculate_exceedence(pots_1xC, covs_abs, scale_fct=cov_scaling_fct)
    xq_values, xq_values_nth = soap.soapy.npfga.rank_ptest(
        tags=tags,
        covs=covs_abs,
        exs=exs,
        exs_cum=ranks_Cx1,
        rand_exs_rank=null_exs_SxC,
        rand_exs_rank_cum=ranks_Sx1)
    if with_stats:
        cstats = PyFGraphStats(tags, covs, covs_abs, cq_values, cq_values_nth, null_order_covs_SxC, null_covs_SxC, cov_scaling_fct)
        xstats = PyFGraphStats(tags, covs, exs, xq_values, xq_values_nth, null_exs_SxC, null_covs_SxC, cov_scaling_fct)
    else:
        cstats = None
        xstats = None
    return null_order_covs_SxC, null_exs_SxC, covs_abs, exs, cstats, xstats

def run_npfga_with_phasing(fgraph, IX, Y, rand_IX_list, rand_Y, options, log):
    log << log.mg << "Running NPFGA with phasing" << log.endl
    # Hard-coded options
    edge_pctile = 100.
    null_edge_pctiles = [ 10. ]
    op_complexity_map = {
       "I": 0.0,
       "r": 0.75,
       "2": 0.75,
       "s": 1.00,
       "|": 1.25,
       "e": 1.50,
       "l": 1.50,
       "*": 1.75,
       ":": 2.00,
       "+": 2.25,
       "-": 2.25
    }
    # Precompute covariances across all channels
    fnodes_all = [ f for f in fgraph ]
    rand_covs_all = fgraph_apply_batch(fgraph, rand_IX_list, rand_Y, log)
    covs_all = fgraph.applyAndCorrelate(
        IX,
        Y.reshape((-1,1)),
        str(IX.dtype))[:,0]
    # Calculate complexities to inform phasing
    fnode_complexities, phase_thresholds = calculate_fnode_complexities(
        fgraph, op_complexity_map)
    phase_null_exs_top = []
    phase_null_cov_top = []
    phase_exs_top = []
    phase_cov_top = []
    phase_feature_idcs = []
    phase_cstats = []
    phase_xstats = []
    # Incrementally grow the active subgraph and evaluate
    for pidx, phase in enumerate(phase_thresholds):
        phase_idcs = np.where(fnode_complexities <= phase)[0]
        log << "Evaluating phase %2d: %5d nodes" % (pidx, len(phase_idcs)) << log.endl
        phase_feature_idcs.append(phase_idcs)
        null_order_covs_SxC, null_exs_SxC, covs, exs, cstats, xstats = calculate_null_and_test(
            tags=[ fnodes_all[_].expr for _ in phase_idcs ],
            covs=covs_all[phase_idcs],
            rand_covs=rand_covs_all[:, phase_idcs],
            options=options,
            log=None, #log,
            with_stats=True)
        phase_cstats.append(cstats)
        phase_xstats.append(xstats)
        # Store phased distributions
        covs_abs = np.abs(covs)
        phase_null_cov_top.append(null_order_covs_SxC[:,0])
        phase_cov_top.append(np.percentile(covs_abs, edge_pctile))
        phase_null_exs_top.append(null_exs_SxC[:,0])
        phase_exs_top.append(np.percentile(exs, edge_pctile))
    phase_null_exs_top = np.array(phase_null_exs_top).T # n_random_samples x n_phases
    phase_null_cov_top = np.array(phase_null_cov_top).T # n_random_samples x n_phases
    phase_exs_top = np.array(phase_exs_top).T # n_phases
    phase_cov_top = np.array(phase_cov_top).T # n_phases
    phase_offset_exs = np.zeros(phase_exs_top.shape, phase_exs_top.dtype)
    phase_offset_cov = np.zeros(phase_cov_top.shape, phase_cov_top.dtype)
    for pct in null_edge_pctiles:
        pct_null_exs = np.percentile(phase_null_exs_top, pct, axis=0)
        pct_null_cov = np.percentile(phase_null_cov_top, pct, axis=0)
        phase_offset_exs = phase_offset_exs + phase_exs_top - pct_null_exs
        phase_offset_cov = phase_offset_cov + phase_cov_top - pct_null_cov
    phase_offset_exs = phase_offset_exs/len(null_edge_pctiles)
    phase_offset_cov = phase_offset_cov/len(null_edge_pctiles)
    return phase_feature_idcs, phase_cstats, phase_xstats, phase_offset_cov, phase_offset_exs

def run_npfga(fgraph, IX, Y, rand_IX_list, rand_Y, options, log):
    """
    Required options fields: bootstrap, tail_fraction
    """
    # C = #channels, S = #samples
    rand_covs = fgraph_apply_batch(fgraph, rand_IX_list, rand_Y, log)
    # TODO For all phases ... >>>
    pots_1xC, ranks_Cx1, ranks_Sx1, null_exs_SxC, null_order_covs_SxC, null_covs_SxC, cov_scaling_fct = soap.soapy.npfga.calculate_null_distribution(
        rand_covs,
        options=options,
        log=log)
    # TODO <<< -> store
    # Bootstrap
    if options.bootstrap == 0:
        data_iterator = zip([0], [IX], [Y])
    elif options.bootstrap_by_mode:
        data_iterator = mode_resample_IX_Y(IX, Y, options.bootstrap, options.bootstrap_mode_threshold)
    else:
        data_iterator = resample_IX_Y(IX, Y, options.bootstrap)
    n_resamples = options.bootstrap if options.bootstrap > 0 else 1
    cov_samples    = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    exs_samples    = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    cq_samples     = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    cq_samples_nth = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    xq_samples     = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    xq_samples_nth = np.zeros((len(fgraph),n_resamples), dtype=IX.dtype)
    for sample_idx, IX_i, Y_i in data_iterator:
        if log: log << log.back << "Resampling idx" << sample_idx << log.flush
        covs = fgraph.applyAndCorrelate(
            IX_i,
            Y_i.reshape((-1,1)),
            str(IX_i.dtype))[:,0]
        tags = [ f.expr for f in fgraph ]
        # TODO For all phases ... >>>
        # Test statistic: abs(cov)
        covs_abs = np.abs(covs)
        cq_values, cq_values_nth = soap.soapy.npfga.rank_ptest(
            tags=tags,
            covs=covs_abs,
            exs=covs_abs,
            exs_cum=ranks_Cx1,
            rand_exs_rank=null_order_covs_SxC,
            rand_exs_rank_cum=ranks_Sx1)
        # Test statistic: exs(cov)
        exs = calculate_exceedence(pots_1xC, covs_abs, scale_fct=cov_scaling_fct)
        xq_values, xq_values_nth = soap.soapy.npfga.rank_ptest(
            tags=tags,
            covs=covs_abs,
            exs=exs,
            exs_cum=ranks_Cx1,
            rand_exs_rank=null_exs_SxC,
            rand_exs_rank_cum=ranks_Sx1)
        cov_samples[:,sample_idx] = covs
        exs_samples[:,sample_idx] = exs
        cq_samples[:,sample_idx] = cq_values
        cq_samples_nth[:,sample_idx] = cq_values_nth
        xq_samples[:,sample_idx] = xq_values
        xq_samples_nth[:,sample_idx] = xq_values_nth
        # TODO <<< store
    if log: log << log.endl
    # Bootstrap avgs and stddevs
    covs = np.average(cov_samples, axis=1)
    covs_std = np.std(cov_samples, axis=1)
    exs = np.average(exs_samples, axis=1)
    exs_std = np.std(exs_samples, axis=1)
    cq_values = np.average(cq_samples, axis=1)
    cq_values_std = np.std(cq_samples, axis=1)
    xq_values = np.average(xq_samples, axis=1)
    xq_values_std = np.std(xq_samples, axis=1)
    cq_values_nth = np.average(cq_samples_nth, axis=1)
    cq_values_nth_std = np.std(cq_samples_nth, axis=1)
    xq_values_nth = np.average(xq_samples_nth, axis=1)
    xq_values_nth_std = np.std(xq_samples_nth, axis=1)
    for fidx, fnode in enumerate(fgraph):
        fnode.q = xq_values[fidx]
        fnode.cov = covs[fidx]
    cstats = PyFGraphStats(tags, covs, covs_abs, cq_values, cq_values_nth, null_order_covs_SxC, null_covs_SxC, cov_scaling_fct)
    xstats = PyFGraphStats(tags, covs, exs, xq_values, xq_values_nth, null_exs_SxC, null_covs_SxC, cov_scaling_fct)
    return tags, covs, covs_std, cq_values, cq_values_std, xq_values, xq_values_std, cstats, xstats

def solve_decomposition_lseq(input_tuples, bar_covs, log=None):
    # Setup linear system A*X = B and solve for x (margin terms)
    A = np.ones((len(input_tuples),len(input_tuples))) # coeff_matrix
    for i, row_tup in enumerate(input_tuples):
        for j, col_tup in enumerate(input_tuples):
            zero = False
            for tag in row_tup:
                if tag in col_tup:
                    zero = True
                    break
            if zero: A[i,j] = 0.0
    covs = np.zeros(shape=bar_covs.shape, dtype=bar_covs.dtype)
    if log: log << "Solving LSEQ" << log.endl
    for sample_idx in range(bar_covs.shape[2]):
        if log: log << log.back << " - Random sample %d" % (sample_idx) << log.flush
        covs[:,:,sample_idx] = np.linalg.solve(A, bar_covs[:,:,sample_idx])
    if log: log << log.endl
    return covs

def get_marginal_tuples(roots, fnodes, log=None):
    root_tags = [ r.expr for r in roots ]
    input_tuples = []
    max_size = max([ len(f.getRoots()) for f in fnodes ])
    if log: log << "Partial randomizations (max degree = %d)" % max_size << log.endl
    for size in range(len(root_tags)+1):
        if size > max_size: break
        tuples = soap.soapy.math.find_all_tuples_of_size(size, root_tags)
        if log: log << " - Degree %d: %d marginals" % (size, len(tuples)) << log.endl
        input_tuples.extend(tuples)
    return input_tuples

def run_cov_decomposition(fgraph, IX, Y, rand_IX_list, rand_Y, bootstrap, log=None):
    log << log.mg << "Nonlinear covariance decomposition" << log.endl
    roots = fgraph.getRoots()
    root_tag_to_idx = { r.expr: ridx for ridx, r in enumerate(roots) }
    input_tuples = get_marginal_tuples(roots, fgraph, log)
    # Calculate partially randomized marginals
    if bootstrap > 0:
        # Bootstrap sampling preps (bootstrap = 0 => no bootstrapping)
        n_resample = bootstrap if bootstrap > 0 else 1
        resample_iterator = resample_range(0, IX.shape[0], bootstrap) if bootstrap > 0 else zip([0], [ np.arange(0, IX.shape[0]) ])
        resample_iterator_reusable = [ r for r in resample_iterator ]
        bar_covs = np.zeros((len(input_tuples), len(fgraph), n_resample), dtype=IX.dtype)
        for tup_idx, tup in enumerate(input_tuples):
            log << "Marginal %d/%d: %s " % (tup_idx+1, len(input_tuples), tup) << log.endl
            rand_covs = np.zeros((len(fgraph), len(rand_IX_list), n_resample), dtype=IX.dtype)
            rand_Y = rand_Y.reshape((-1,1))
            for i in range(len(rand_IX_list)):
                rand_IX = np.copy(IX)
                for tag in tup:
                    rand_IX[:,root_tag_to_idx[tag]] = rand_IX_list[i][:,root_tag_to_idx[tag]]
                log << log.back << " - Randomized control, instance" << i << log.flush
                rand_IX_up = fgraph.apply(rand_IX, str(rand_IX.dtype))
                for boot_idx, idcs in resample_iterator_reusable:
                    y_norm = (Y[idcs]-np.average(Y[idcs]))/np.std(Y[idcs])
                    IX_up_norm, mean, std = zscore(rand_IX_up[idcs])
                    rand_covs[:,i,boot_idx] = IX_up_norm.T.dot(y_norm)/y_norm.shape[0]
            log << log.endl
            bar_covs[tup_idx,:,:] = np.average(rand_covs, axis=1)
    else:
        bar_covs = np.zeros((len(input_tuples), len(fgraph), len(rand_IX_list)), dtype=IX.dtype)
        for tup_idx, tup in enumerate(input_tuples):
            log << "Marginal %d/%d: %s " % (tup_idx+1, len(input_tuples), tup) << log.endl
            rand_covs = np.zeros((len(fgraph), len(rand_IX_list)), dtype=IX.dtype)
            rand_Y = rand_Y.reshape((-1,1))
            for i in range(len(rand_IX_list)):
                rand_IX = np.copy(IX)
                for tag in tup:
                    rand_IX[:,root_tag_to_idx[tag]] = rand_IX_list[i][:,root_tag_to_idx[tag]]
                log << log.back << " - Randomized control, instance" << i << log.flush
                rand_covs[:,i] = fgraph.applyAndCorrelate(rand_IX, rand_Y, str(IX.dtype))[:,0]
            log << log.endl
            bar_covs[tup_idx,:,:] = rand_covs
    # Solve linear system for decomposition
    covs = solve_decomposition_lseq(input_tuples, bar_covs, log=log)
    covs_avg = np.average(covs, axis=2)
    covs_std = np.std(covs, axis=2)
    return input_tuples, covs_avg, covs_std

def run_cov_decomposition_filter(fgraph, order, IX, Y, rand_IX_list, rand_Y, bootstrap, log):
    fnodes = [ f for f in fgraph ]
    log << log.mg << "Cov decomposition filter" << log.endl
    keep = True
    selected_idx = None
    scores = []
    root_contributions_list = []
    for rank in xrange(-1,-len(order)-1,-1):
        fnode = fnodes[order[rank]]
        row_tuples, cov_decomposition, cov_decomposition_std = soap.soapy.npfga.run_cov_decomposition_single(
            fgraph=fgraph,
            fnode=fnode,
            IX=IX,
            Y=Y,
            rand_IX_list=rand_IX_list,
            rand_Y=rand_Y,
            bootstrap=bootstrap,
            log=log)
        row_order = np.argsort(cov_decomposition[:,0])
        for r in row_order:
            log << "i...j = %-50s  cov(i..j) = %+1.4f (+-%1.4f)" % (
                row_tuples[r], cov_decomposition[r,0], cov_decomposition_std[r,0]) << log.endl
        root_tags = [ r.expr for r in fnode.getRoots() ]
        root_contributions = { t: { "cov": [], "std": [] } for t in root_tags }
        total_cov = np.sum(cov_decomposition)
        log << "Total covariance for this channel is" << total_cov << log.endl
        keep = True
        for r in root_tags:
            for row_idx, row_tuple in enumerate(row_tuples):
                if r in row_tuple:
                    root_contributions[r]["cov"].append(cov_decomposition[row_idx,0]/len(row_tuple))
                    root_contributions[r]["std"].append(cov_decomposition_std[row_idx,0])
            cov = np.array(root_contributions[r]["cov"])
            std = np.array(root_contributions[r]["std"])
            cov = np.sum(cov)
            std = (std.dot(std))**0.5
            root_contributions[r]["cov"] = cov
            root_contributions[r]["std"] = std
            if np.abs(cov) < 3.*std or cov*total_cov < 0.: # i.e., not significant or anticorrelated
                flag = 'x'
                keep = False
            else:
                flag = ''
            log << "x=%s => rho1(x) = %+1.4f +- %+1.4f    %s" % (r, cov, std, flag) << log.endl
        if keep:
            selected_idx = order[rank]
            #break
        delta = np.std([ root_contributions[r]["cov"] for r in root_tags ])
        log << "  => Score = |%1.4f| - %1.4f" % (total_cov, delta) << log.endl
        if np.isnan(delta):
            log << log.mr << "WARNING: NAN in covariance decomposition" << log.endl
        else:
            scores.append([ rank, np.abs(total_cov)-delta ])
        root_contributions_list.append([ fnode.expr, root_contributions])
    scores = sorted(scores, key=lambda s: -s[1])
    #if selected_idx is None: raise RuntimeError("Filter returned none")
    selected_idx = order[scores[0][0]]
    return selected_idx, root_contributions_list

def run_cov_decomposition_single(fgraph, fnode, IX, Y, rand_IX_list, rand_Y, bootstrap, log):
    log << log.mg << "Nonlinear covariance decomposition for '%s'" % fnode.expr << log.endl
    roots = fnode.getRoots()
    roots_all = fgraph.getRoots()
    root_tag_to_idx = { r.expr: ridx for ridx, r in enumerate(roots_all) }
    input_tuples = get_marginal_tuples(roots, [ fnode ], log)
    # Bootstrap sampling preps (bootstrap = 0 => no bootstrapping)
    n_resample = bootstrap if bootstrap > 0 else 1
    resample_iterator = resample_range(0, IX.shape[0], bootstrap) if bootstrap > 0 else zip([0], [ np.arange(0, IX.shape[0]) ])
    resample_iterator_reusable = [ r for r in resample_iterator ]
    # Calculate partially randomized marginals
    bar_covs = np.zeros((len(input_tuples), 1, n_resample), dtype=IX.dtype) # marginals x channels x resample
    for tup_idx, tup in enumerate(input_tuples):
        log << "Marginal %d/%d: %s " % (tup_idx+1, len(input_tuples), tup) << log.endl
        rand_covs = np.zeros((1, len(rand_IX_list), n_resample), dtype=IX.dtype) # channels x samples x resample
        rand_Y = rand_Y.reshape((-1,1))
        for i in range(len(rand_IX_list)):
            rand_IX = np.copy(IX)
            for tag in tup:
                rand_IX[:,root_tag_to_idx[tag]] = rand_IX_list[i][:,root_tag_to_idx[tag]]
            log << log.back << " - Randomized control, instance" << i << log.flush
            rand_x = fgraph.evaluateSingleNode(fnode, rand_IX, str(rand_IX.dtype))[:,0]
            for boot_idx, idcs in resample_iterator_reusable:
                y_norm = (Y[idcs]-np.average(Y[idcs]))/np.std(Y[idcs])
                x_norm = (rand_x[idcs] - np.average(rand_x[idcs]))/np.std(rand_x[idcs])
                rand_covs[0,i,boot_idx] = np.dot(x_norm, y_norm)/y_norm.shape[0]
        log << log.endl
        bar_covs[tup_idx,0,:] = np.average(rand_covs, axis=1)
    # Solve linear system for decomposition
    covs = solve_decomposition_lseq(input_tuples, bar_covs)
    covs_avg = np.average(covs, axis=2)
    covs_std = np.std(covs, axis=2)
    return input_tuples, covs_avg, covs_std

def calculate_root_weights(fgraph, q_values, row_tuples, cov_decomposition, log=None):
    if log: log << log.mg << "Calculating root weights from covariance decomposition" << log.endl
    root_tags = [ r.expr for r in fgraph.getRoots() ]
    row_idcs_non_null = filter(lambda i: len(row_tuples[i]) > 0, np.arange(len(row_tuples)))
    row_tuples_non_null = filter(lambda t: len(t) > 0, row_tuples)
    row_weights_non_null = [ 1./len(tup) for tup in row_tuples_non_null ]
    col_signs = np.sign(np.sum(cov_decomposition[row_idcs_non_null], axis=0))
    col_weights = np.array(q_values)
    tuple_weights = np.sum(cov_decomposition[row_idcs_non_null]*col_signs*col_weights, axis=1)
    root_counts = { root_tag: 0 for root_tag in root_tags }
    for f in fgraph:
        for r in f.getRoots(): root_counts[r.expr] += 1
    root_weights = { root_tag: 0 for root_tag in root_tags }
    for tupidx, tup in enumerate(row_tuples_non_null):
        for t in tup:
            root_weights[t] += 1./len(tup)*tuple_weights[tupidx]
    for r in root_weights: root_weights[r] /= root_counts[r]
    root_tags_sorted = sorted(root_tags, key=lambda t: root_weights[t])
    if log: log << "Tuple weight" << log.endl
    for tup_idx, tup in enumerate(row_tuples_non_null):
        if log: log << "i...j = %-50s  w(i...j) = %1.4e" % (':'.join(tup), tuple_weights[tup_idx]) << log.endl
    if log: log << "Aggregated root weight" << log.endl
    for r in root_tags_sorted:
        if log: log << "i = %-50s  w0(i) = %1.4e   (# derived nodes = %d)" % (r, root_weights[r], root_counts[r]) << log.endl
    return root_tags_sorted, root_weights, root_counts

def run_factor_analysis(mode, fgraph, fnode, IX, Y, rand_IX_list, rand_Y, ftag_to_idx, log):
    roots = fnode.getRoots()
    root_tags = [ (r.tag[2:-1] if r.tag.startswith("(-") else r.tag) for r in roots ]
    # Covariance for true instantiation
    x = fgraph.evaluateSingleNode(fnode, IX, str(IX.dtype))
    x_norm = (x[:,0]-np.average(x[:,0]))/np.std(x)
    y_norm = (Y-np.average(Y))/np.std(Y)
    cov = np.dot(x_norm, y_norm)/y_norm.shape[0]
    # Null dist
    rand_covs_base = []
    for i in range(len(rand_IX_list)):
        rand_x = fgraph.evaluateSingleNode(fnode, rand_IX_list[i], str(rand_IX_list[i].dtype))
        rand_x_norm = (rand_x[:,0] - np.average(rand_x[:,0]))/np.std(rand_x[:,0])
        rand_cov = np.dot(rand_x_norm, y_norm)/y_norm.shape[0]
        rand_covs_base.append(np.abs(rand_cov))
    rand_covs_base = np.array(sorted(rand_covs_base))
    np.savetxt('out_null.txt', np.array([np.arange(len(rand_covs_base))/float(len(rand_covs_base)), rand_covs_base]).T)
    # Analyse each factor
    factor_map = {}
    for root_tag in root_tags:
        rand_covs = []
        for i in range(len(rand_IX_list)):
            rand_IX = np.copy(IX)
            if mode == "randomize_this":
                rand_IX[:,ftag_to_idx[root_tag]] = rand_IX_list[i][:,ftag_to_idx[root_tag]]
            elif mode == "randomize_other":
                for tag in root_tags:
                    if tag == root_tag: pass
                    else: rand_IX[:,ftag_to_idx[tag]] = rand_IX_list[i][:,ftag_to_idx[tag]]
            else: raise ValueError(mode)
            rand_x = fgraph.evaluateSingleNode(fnode, rand_IX, str(rand_IX.dtype))
            rand_x_norm = (rand_x[:,0] - np.average(rand_x[:,0]))/np.std(rand_x[:,0])
            rand_cov = np.dot(rand_x_norm, y_norm)/y_norm.shape[0]
            rand_covs.append(np.abs(rand_cov))
        # Test
        rand_covs = np.array(sorted(rand_covs))
        np.savetxt('out_%s_%s.txt' % (mode.split("_")[1], root_tag), np.array([np.arange(len(rand_covs))/float(len(rand_covs)), rand_covs]).T)
        rank = np.searchsorted(rand_covs, np.abs(cov))
        q_value = float(rank)/len(rand_covs)
        factor_map[root_tag] = { "q_value": q_value, "min_cov": rand_covs[0], "max_cov": rand_covs[-1] }
    for factor, r in factor_map.iteritems():
        log << "%-50s c=%+1.4f q%-20s = %+1.4f  [random min=%1.2f max=%1.2f]" % (
            fnode.expr, cov, "(%s)" % factor, r["q_value"], r["min_cov"], r["max_cov"]) << log.endl
    return factor_map

def represent_graph_2d_linear(
        fgraph, 
        root_weights, 
        alpha, 
        weight_fct=lambda f: np.abs(f.cov*f.confidence)):
    # POSITION NODES
    scale = 10
    dy_root = scale*5./len(fgraph.map_generations[0])
    y_max = scale*5.
    x_offset = 0.0
    x_root = scale*0.5
    qc_scale = scale*0.0

    unary_offset = [ None, 0.55*x_root ]
    unary_offset_y = [ None, 0. ]
    unary_op_offset = { 
        "e": [ 0.0, 1.0 ],
        "l": [ -1.0, 0.5 ],
        "|": [ +1.0, 0.5 ],
        "s": [ -1.0, -0.5 ],
        "r": [ +1.0, -0.5 ],
        "2": [ 0.0, -1.0 ]
    }
    binary_offset = [ None, 1.55*x_root, 3*x_root ]
    binary_offset_y = [ None, 0., 0. ]
    root_off = 0.0
    w_avg = np.average([ w for r,w in root_weights.iteritems() ])

    dy_map = {}
    for gen in fgraph.generations:
        nodes = fgraph.map_generations[gen]
        print "Positioning generation", gen
        for idx, node in enumerate(nodes):
            if gen == 0:
                w = root_weights[node.expr]
                node.x = x_offset
                dy = w/w_avg*dy_root
                dy_map[node.expr] = dy
                node.y = root_off + 0.5*dy
                y_max = node.y
                root_off += dy
                print "x=%1.2f y=%1.2f %s" % (node.x, node.y, node.expr)
            elif len(node.parents) == 1:
                # Unary case
                par = node.parents[0]
                #node.x = unary_offset[gen] + qc_scale*weight_fct(node) + x_offset
                node.x = unary_offset[gen] + qc_scale*weight_fct(node) + x_offset + 0.1*unary_offset[gen]*unary_op_offset[node.fnode_.op_tag][0]
                #node.y = unary_offset_y[gen] + 0.0*dy_root + par.y + 1.0*weight_fct(node)**2
                node.y = unary_offset_y[gen] + 0.0*dy_root + par.y + 0.2*dy_map[par.expr]*unary_op_offset[node.fnode_.op_tag][1]
            elif len(node.parents) == 2:
                # Binary case
                p1 = node.parents[0]
                p2 = node.parents[1]
                y_parents = sorted([ p.y for p in node.parents ])
                dy = y_parents[1]-y_parents[0]
                node.x = 0.05*(p2.y-p1.y) + binary_offset[gen] + qc_scale*(
                    weight_fct(node)) + x_offset
                #node.y = 0.5*(p1.y+p2.y) + qc_scale*(
                #    np.abs(node.cov*node.confidence)**2)

                #w1 = np.exp(-0.002*p1.y**1) + np.exp(-0.001*(y_max-p1.y)**2)
                #w2 = np.exp(-0.002*p2.y**1) + np.exp(-0.001*(y_max-p2.y)**2)
                #z12 = w1+w2
                #w1 = w1/z12
                #w2 = w2/z12
                w1 = w2 = 0.5
                #print w1, w2, p1.y, p2.y, w1*p1.y+w2*p2.y
                node.y = binary_offset_y[gen] + w1*p1.y+w2*p2.y + qc_scale*(
                    weight_fct(node)**2)
    # LINKS BETWEEN NODES
    def connect_straight(f1, f2):
        x1 = f1.x
        y1 = f1.y
        x2 = f2.x
        y2 = f2.y
        #w = np.abs(f2.cov*f2.confidence)
        #w = f2.rank
        w = weight_fct(f2)
        return [ [x1,y1,w], [x2,y2,w] ]
    def connect_tanh(f0, f1, f2, samples=30, alpha=alpha):
        x1 = f1.x
        y1 = f1.y
        x2 = f2.x
        y2 = f2.y
        #w = f2.rank
        w = weight_fct(f2)
        coords = []
        for i in range(samples):
            xi = x1 + float(i)/(samples-1)*(x2-x1)
            yi = y1 + (y2-y1)*0.5*(1 + np.tanh(alpha*(xi - 0.5*(x1+x2))))
            coords.append([xi, yi, w])
        return coords
    def connect_arc(f0, f1, f2, samples=30):
        x0 = f0.x
        y0 = f0.y
        x1 = f1.x
        y1 = f1.y
        x2 = f2.x
        y2 = f2.y
        #w = np.abs(f2.cov*f2.confidence)
        #w = f2.rank
        w = weight_fct(f2)
        r1 = ((x1-x0)**2+(y1-y0)**2)**0.5
        r2 = ((x2-x0)**2+(y2-y0)**2)**0.5
        phi1 = np.arctan2(y1-y0, x1-x0)
        phi2 = np.arctan2(y2-y0, x2-x0)
        if phi1 < 0.: phi1 = 2*np.pi + phi1
        if phi2 < 0.: phi2 = 2*np.pi + phi2
        phi_start = phi1
        dphi = phi2-phi1
        if dphi >= np.pi:
            dphi = 2*np.pi - dphi
            phi_end = phi_start-dphi
        elif dphi <= -np.pi:
            dphi = 2*np.pi + dphi
            phi_end = phi_start+dphi
        else:
            phi_end = phi_start + dphi
        coords = []
        for i in range(samples):
            phi_i = phi_start + float(i)/(samples-1)*(phi_end-phi_start)
            rad_i = r1 + float(i)/(samples-1)*(r2-r1)
            x_i = x0 + rad_i*np.cos(phi_i)
            y_i = y0 + rad_i*np.sin(phi_i)
            coords.append([x_i, y_i, w])
        return coords
    curves = []
    curve_info = []
    for fnode in fgraph.fnodes:
        if len(fnode.parents) == 1:
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[0].expr })
            #curves.append(connect_straight(fnode.parents[0], fnode))
            curves.append(connect_tanh(None, fnode.parents[0], fnode, alpha=3*alpha))
        elif len(fnode.parents) == 2:
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[0].expr })
            curves.append(connect_tanh(fnode.parents[0], fnode.parents[1], fnode))
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[1].expr })
            curves.append(connect_tanh(fnode.parents[1], fnode.parents[0], fnode))
        else: pass
    # Sort curves so important ones are in the foreground
    order = np.argsort([ c[0][-1] for c in curves ])
    #curves = sorted(curves, key=lambda c: c[0][-1])
    curves = [ curves[_] for _ in order ]
    curve_info = [ curve_info[_] for _ in order]
    return fgraph, curves, curve_info

def represent_graph_2d(fgraph):
    # POSITION NODES
    dphi_root = 2*np.pi/len(fgraph.map_generations[0])
    radius_offset = 0.0
    radius_root = 1.0
    radius_scale = 2.5
    for gen in fgraph.generations:
        nodes = fgraph.map_generations[gen]
        print "Positioning generation", gen
        for idx, node in enumerate(nodes):
            if gen == 0:
                node.radius = radius_root + radius_offset
                node.phi = idx*dphi_root
                print "r=%1.2f phi=%1.2f %s" % (node.radius, node.phi, node.expr)
            elif len(node.parents) == 1:
                # Unary case
                par = node.parents[0]
                node.radius = (1.+gen-0.3)**2*radius_root + radius_scale*(
                    np.abs(node.cov*node.confidence))*radius_root + radius_offset
                node.phi = par.phi + (
                    np.abs(node.cov*node.confidence))*dphi_root/node.radius
            elif len(node.parents) == 2:
                # Binary case
                p1 = node.parents[0]
                p2 = node.parents[1]
                phi_parents = sorted([ p.phi for p in node.parents ])
                dphi = phi_parents[1]-phi_parents[0]
                if dphi <= np.pi:
                    node.phi = phi_parents[0] + 0.5*dphi
                else:
                    node.phi = (phi_parents[1] + 0.5*(2*np.pi - dphi)) % (2*np.pi)
                node.radius = (1.+gen+(0.2 if gen < 2 else 0))**2*radius_root + radius_scale*(
                    np.abs(node.cov*node.confidence))*radius_root + radius_offset
                node.phi = node.phi + (
                    np.abs(node.cov*node.confidence))*dphi_root/node.radius
    # LINKS BETWEEN NODES
    def connect_straight(f1, f2):
        x1 = f1.radius*np.cos(f1.phi)
        y1 = f1.radius*np.sin(f1.phi)
        x2 = f2.radius*np.cos(f2.phi)
        y2 = f2.radius*np.sin(f2.phi)
        #w = np.abs(f2.cov*f2.confidence)
        w = f2.rank
        return [ [x1,y1,w], [x2,y2,w] ]
    def connect_arc(f0, f1, f2, samples=15):
        x0 = f0.radius*np.cos(f0.phi)
        y0 = f0.radius*np.sin(f0.phi)
        x1 = f1.radius*np.cos(f1.phi)
        y1 = f1.radius*np.sin(f1.phi)
        x2 = f2.radius*np.cos(f2.phi)
        y2 = f2.radius*np.sin(f2.phi)
        #w = np.abs(f2.cov*f2.confidence)
        w = f2.rank
        r1 = ((x1-x0)**2+(y1-y0)**2)**0.5
        r2 = ((x2-x0)**2+(y2-y0)**2)**0.5
        phi1 = np.arctan2(y1-y0, x1-x0)
        phi2 = np.arctan2(y2-y0, x2-x0)
        if phi1 < 0.: phi1 = 2*np.pi + phi1
        if phi2 < 0.: phi2 = 2*np.pi + phi2
        phi_start = phi1
        dphi = phi2-phi1
        if dphi >= np.pi:
            dphi = 2*np.pi - dphi
            phi_end = phi_start-dphi
        elif dphi <= -np.pi:
            dphi = 2*np.pi + dphi
            phi_end = phi_start+dphi
        else:
            phi_end = phi_start + dphi
        coords = []
        for i in range(samples):
            phi_i = phi_start + float(i)/(samples-1)*(phi_end-phi_start)
            rad_i = r1 + float(i)/(samples-1)*(r2-r1)
            x_i = x0 + rad_i*np.cos(phi_i)
            y_i = y0 + rad_i*np.sin(phi_i)
            coords.append([x_i, y_i, w])
        return coords
    curves = []
    curve_info = []
    for fnode in fgraph.fnodes:
        if len(fnode.parents) == 1:
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[0].expr })
            curves.append(connect_straight(fnode.parents[0], fnode))
        elif len(fnode.parents) == 2:
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[0].expr })
            curves.append(connect_arc(fnode.parents[0], fnode.parents[1], fnode))
            curve_info.append({ "target": fnode.expr, "source": fnode.parents[1].expr })
            curves.append(connect_arc(fnode.parents[1], fnode.parents[0], fnode))
        else: pass
    # Sort curves so important ones are in the foreground
    order = np.argsort([ c[0][-1] for c in curves ])
    #curves = sorted(curves, key=lambda c: c[0][-1])
    curves = [ curves[_] for _ in order ]
    curve_info = [ curve_info[_] for _ in order]
    return fgraph, curves, curve_info

class RandomizeMatrix(object):
    def __init__(self, method):
        self.method = method
    def sample(self, X, n_samples, seed=None, log=None):
        rnd_X_list = []
        if seed != None: np.random.seed(seed)
        if self.method == "perm_within_cols":
            for i in range(n_samples):
                if log: log << log.back << "Random feature set" << i << log.flush
                rnd_X = np.copy(X)
                for col in range(X.shape[1]):
                    np.random.shuffle(rnd_X[:,col])
                rnd_X_list.append(rnd_X)
        elif self.method == "perm_rows":
            for i in range(n_samples):
                if log: log << log.back << "Random feature set" << i << log.flush
                rnd_X = np.copy(X)
                np.random.shuffle(rnd_X)
                rnd_X_list.append(rnd_X)
        else: raise ValueError(self.method)
        if log: log << log.endl
        return rnd_X_list

class CVLOO(object):
    def __init__(self, state, options):
        self.tag = "cv_loo"
        self.n_samples = len(state)
        self.n_reps = len(state)
        self.step = 0
    def next(self):
        assert not self.isDone()
        info = "%s_i%03d" % (self.tag, self.step)
        idcs_train = list(np.arange(self.step)) + list(np.arange(self.step+1, self.n_samples))
        idcs_test = [ self.step ]
        self.step += 1
        return info, idcs_train, idcs_test
    def isDone(self):
        return self.step >= self.n_reps

class CVMC(object):
    def __init__(self, state, options):
        self.tag = "cv_mc"
        self.n_samples = state if (type(state) is int) else len(state)
        self.n_reps = options.n_mccv
        self.f_mccv = options.f_mccv
        self.step = 0
    def next(self):
        assert not self.isDone()
        info = "%s_i%03d" % (self.tag, self.step)
        idcs = np.arange(self.n_samples)
        np.random.shuffle(idcs)
        split_at = int(self.f_mccv*self.n_samples)
        idcs_train = idcs[0:split_at]
        idcs_test = idcs[split_at:]
        self.step += 1
        return info, idcs_train, idcs_test
    def isDone(self):
        return self.step >= self.n_reps

class CVCustom(object):
    def __init__(self, state, options):
        self.tag = "cv_custom"
        self.n_samples = len(state)
        self.splits = json.load(open(options.splits_json))
        self.n_reps = len(self.splits)
        self.step = 0
    def next(self):
        assert not self.isDone()
        info = "%s_i%03d" % (self.tag, self.step)
        idcs_test = self.splits[self.step]["idcs_test"]
        mask = np.ones((self.n_samples,), dtype='i8')
        mask[idcs_test] = 0
        idcs_train = np.where(mask > 0)[0]
        idcs_test = np.where(mask == 0)[0]
        self.step += 1
        return info, idcs_train, idcs_test
    def isDone(self):
        return self.step >= self.n_reps

class CVUser(object):
    def __init__(self, state, options):
        self.tag = "cv_user"
        self.n_samples = len(state)
        self.n_reps = 1
        self.step = 0
        self.mask = np.ones((self.n_samples,), dtype='i8')
        self.mask[options.test_on] = 0
    def next(self):
        assert not self.isDone()
        info = "%s_i%03d" % (self.tag, self.step)
        idcs_train = np.where(self.mask > 0)[0]
        idcs_test = np.where(self.mask == 0)[0]
        self.step += 1
        return info, idcs_train, idcs_test
    def isDone(self):
        return self.step >= self.n_reps

class CVNone(object):
    def __init__(self, state, options):
        self.tag = "cv_no"
        self.n_samples = len(state)
        self.n_reps = 1
        self.step = 0
    def next(self):
        assert not self.isDone()
        info = "%s_i%03d" % (self.tag, self.step)
        idcs_train = np.arange(self.n_samples)
        idcs_test = []
        self.step += 1
        return info, idcs_train, idcs_test
    def isDone(self):
        return self.step >= self.n_reps

def CVIter(tags, options):
    return cv_iterator[options.cv_mode](tags, options)

cv_iterator = {
  "loo": CVLOO,
  "mc": CVMC,
  "user": CVUser,
  "none": CVNone,
  "custom": CVCustom
}

def metric_mse(yp,yt):
    return np.sum((yp-yt)**2)/yp.shape[0]

def metric_rmse(yp,yt):
    return metric_mse(yp,yt)**0.5

def metric_mae(yp,yt):
    return np.sum(np.abs(yp-yt))/yp.shape[0]

def metric_rhop(yp,yt):
    return scipy.stats.pearsonr(yp, yt)[0]

def metric_rhor(yp,yt):
    return scipy.stats.spearmanr(yp, yt).correlation

def metric_auc(yp,yt):
    import sklearn.metrics
    return sklearn.metrics.roc_auc_score(yt,yp)

class CVEval(object):
    eval_map = { 
        "mae": metric_mae,
        "mse": metric_mse,
        "rmse": metric_rmse, 
        "rhop": metric_rhop,
        "auc":  metric_auc
    }
    def __init__(self, jsonfile=None):
        self.yp_map = {}
        self.yt_map = {}
        if jsonfile is not None: self.load(jsonfile)
        return
    def append(self, channel, yp, yt):
        if not channel in self.yp_map:
            self.yp_map[channel] = []
            self.yt_map[channel] = []
        self.yp_map[channel] = self.yp_map[channel] + list(yp)
        self.yt_map[channel] = self.yt_map[channel] + list(yt)
        return
    def evaluate(self, channel, metric, bootstrap=0):
        if len(self.yp_map[channel]) < 1: return np.nan
        if bootstrap == 0:
            return CVEval.eval_map[metric](
                np.array(self.yp_map[channel]), 
                np.array(self.yt_map[channel])), 0.
        else:
            v = []
            n = len(self.yp_map[channel])
            yp = np.array(self.yp_map[channel])
            yt = np.array(self.yt_map[channel])
            for r in range(bootstrap):
                re = np.random.randint(0, n, size=(n,))
                v.append(CVEval.eval_map[metric](yp[re], yt[re]))
            return np.mean(v), np.std(v)
    def evaluateNull(self, channel, metric, n_samples):
        if len(self.yp_map[channel]) < 1: return np.nan
        z = []
        for i in range(n_samples):
            yp_null = np.array(self.yp_map[channel])
            yt_null = np.array(self.yt_map[channel])
            np.random.shuffle(yp_null)
            z.append(CVEval.eval_map[metric](
                yp_null, yt_null))
        z = np.sort(np.array(z))
        return z
    def evaluateAll(self, metrics, bootstrap=0, log=None):
        res = {}
        for channel in sorted(self.yp_map):
            res[channel] = {}
            vs = []
            dvs = []
            for metric in metrics:
                v, dv = self.evaluate(channel, metric, bootstrap=bootstrap)
                res[channel][metric] = v
                res[channel][metric+"_std"] = dv
                vs.append(v)
                dvs.append(dv)
            if log:
                log << "%-9s : " % (channel) << log.flush
                for v, metric in zip(vs, metrics):
                    log << "%s=%+1.4e +- %+1.4e" % (
                        metric, v, dv) << log.flush
                log << log.endl
        return res
    def save(self, jsonfile):
        json.dump({ "yp_map": self.yp_map, "yt_map": self.yt_map },
            open(jsonfile, "w"), indent=1, sort_keys=True)
        return
    def load(self, jsonfile):
        data = json.load(open(jsonfile))
        self.yp_map = data["yp_map"]
        self.yt_map = data["yt_map"]
        return

class LSE(object):
    """Bootstrapper operating on user-specified prediction model

    Parameters
    ----------
    method: bootstrapping approach, can be 'samples', 'residuals' or 'features'
    bootstraps: number of bootstrap samples
    model: regressor/classifier object, e.g., sklearn.linear_model.LinearRegression,
        must implement fit and predict methods
    model_args: constructor arguments for model object
    """
    def __init__(self, **kwargs):
        self.method = kwargs["method"]
        self.bootstraps = kwargs["bootstraps"]
        self.model = kwargs["model"]
        self.model_args = kwargs["model_args"] if "model_args" in kwargs else {}
        self.ensemble = []
        self.feature_weights = None
    def fit(self, IX_train, Y_train, feature_weights=None):
        self.ensemble = []
        sample_iterator = resample_range(0, IX_train.shape[0], IX_train.shape[0])
        if self.method == 'samples':
            while len(self.ensemble) < self.bootstraps:
                resample_idcs = np.random.randint(IX_train.shape[0], size=(IX_train.shape[0],))
                m = self.model(**self.model_args)
                Y_train_boot = Y_train[resample_idcs]
                if np.std(Y_train_boot) < 1e-10: continue
                m.fit(IX_train[resample_idcs], Y_train[resample_idcs])
                self.ensemble.append(m)
        elif self.method == 'residuals':
            m = self.model(**self.model_args)
            m.fit(IX_train, Y_train)
            Y_train_pred = m.predict(IX_train)
            residuals = Y_train - Y_train_pred
            for bootidx in range(self.bootstraps):
                resample_idcs = np.random.randint(IX_train.shape[0], size=(IX_train.shape[0],))
                Y_train_resampled = Y_train + residuals[resample_idcs]
                m = self.model(**self.model_args)
                m.fit(IX_train, Y_train_resampled)
                self.ensemble.append(m)
        elif self.method == 'none':
            m = self.model(**self.model_args)
            m.fit(IX_train, Y_train)
            self.ensemble.append(m)
        elif self.method == 'features':
            if feature_weights is None: feature_weights = np.ones((IX_train.shape[1],))
            self.feature_weights = feature_weights
            self.feature_idcs = []
            n_features = IX_train.shape[1]
            weights = []
            for fidx in range(n_features):
                print "Ensemble for feature", fidx
                if self.bootstraps > 0:
                    for bootidx in range(self.bootstraps):
                        resample_idcs = np.random.randint(IX_train.shape[0], size=(IX_train.shape[0],))
                        m = self.model(**self.model_args)
                        m.fit(IX_train[resample_idcs][:, [fidx]], Y_train[resample_idcs])
                        self.ensemble.append(m)
                        self.feature_idcs.append([fidx])
                        weights.append(feature_weights[fidx])
                else:
                    m = self.model(**self.model_args)
                    m.fit(IX_train[:,[fidx]], Y_train)
                    self.ensemble.append(m)
                    y = m.predict(IX_train[:,[fidx]])
                    self.feature_idcs.append([fidx])
                    weights.append(feature_weights[fidx])
            self.feature_weights = np.array(weights)
        else: raise ValueError(self.method)
    def predict(self, IX):
        Y_pred = []
        if self.method == 'features':
            for midx, m in enumerate(self.ensemble):
                Y_pred.append(m.predict(IX[:,self.feature_idcs[midx]]))
            Y_pred = np.array(Y_pred)
            Y_pred_med = []
            Y_pred_std = []
            for n in range(IX.shape[0]):
                y = Y_pred[:,n]
                order = np.argsort(y)
                y = y[order]
                w = self.feature_weights[order]
                w = np.cumsum(w)
                w = w/w[-1]
                s = np.searchsorted(w, 0.5)
                Y_pred_med.append(0.5*(y[s-1]+y[s]))
                Y_pred_std.append(np.std(y))
            avg = np.array(Y_pred_med)
            std = np.array(Y_pred_std)
            #avg = np.sum((Y_pred.T*self.feature_weights)/np.sum(self.feature_weights), axis=1)
            #std = np.sum((((Y_pred-avg)**2).T*self.feature_weights)/np.sum(self.feature_weights), axis=1)**0.5
            #avg = np.median(Y_pred, axis=0)
            #std = np.std(Y_pred, axis=0)
        else:
            for m in self.ensemble:
                Y_pred.append(m.predict(IX))
            Y_pred = np.array(Y_pred)
            avg = np.median(Y_pred, axis=0)
            std = np.std(Y_pred, axis=0)
        return avg, std

class Booster(object):
    def __init__(self, options):
        self.options = options
        self.initialized = False
        # Cleared whenever dispatched with iter=0
        self.IX_trains = []
        self.Y_trains = []
        self.IX_tests = []
        self.Y_tests = []
        self.iteration = None
        # Kept across dispatches
        self.iteration_train_preds = {}
        self.iteration_train_trues = {}
        self.iteration_preds = {}
        self.iteration_trues = {}
        self.regressors = []
    def dispatchY(self, iteration, Y_train, Y_test):
        self.iteration = iteration
        if self.iteration == 0:
            self.IX_trains = []
            self.Y_trains = [ Y_train ]
            self.IX_tests = []
            self.Y_tests = [ Y_test ]
        if not self.iteration in self.iteration_preds:
            self.iteration_preds[self.iteration] = []
            self.iteration_trues[self.iteration] = []
            self.iteration_train_preds[self.iteration] = []
            self.iteration_train_trues[self.iteration] = []
    def dispatchX(self, iteration, IX_train, IX_test):
        assert iteration == self.iteration # Need to ::dispatchY first
        self.IX_trains.append(IX_train)
        self.IX_tests.append(IX_test)
    def getResidues(self):
        if self.iteration == 0:
            return self.Y_trains[0], self.Y_tests[0]
        else:
            return self.Y_trains[-1]-self.Y_trains[0], self.Y_tests[-1]-self.Y_tests[0]
    def train(self, regressor='lse', bootstraps=1000, method='samples', feature_weights=None, model_args={}):
        if type(regressor) == str and regressor == 'lse':
            import sklearn.linear_model
            model = sklearn.linear_model.LinearRegression
            regressor = LSE(bootstraps=bootstraps, method=method, model=model, model_args=model_args)
        elif type(regressor) == str and regressor == 'logit':
            import sklearn.linear_model
            model = sklearn.linear_model.LogisticRegression
            regressor = LSE(bootstraps=bootstraps, method=method, model=model, model_args=model_args)
        IX_train = np.concatenate(self.IX_trains, axis=1)
        Y_train = self.Y_trains[0]
        if feature_weights is None: regressor.fit(IX_train, Y_train)
        else: regressor.fit(IX_train, Y_train, feature_weights=feature_weights)
        self.regressors.append(regressor)
    def evaluate(self, method='moment'):
        IX_train = np.concatenate(self.IX_trains, axis=1)
        IX_test = np.concatenate(self.IX_tests, axis=1)
        Y_train = self.Y_trains[0]
        Y_test = self.Y_tests[0]
        Y_pred_train_avg, Y_pred_train_std = self.applyLatest(IX_train)
        Y_pred_test_avg, Y_pred_test_std = self.applyLatest(IX_test)
        # Log results
        self.iteration_train_preds[self.iteration].append(np.array([Y_pred_train_avg, Y_pred_train_std]).T)
        self.iteration_train_trues[self.iteration].append(Y_train.reshape((-1,1)))
        if IX_test.shape[0] > 0:
            self.iteration_preds[self.iteration].append(np.array([Y_pred_test_avg, Y_pred_test_std]).T)
            self.iteration_trues[self.iteration].append(Y_test.reshape((-1,1)))
        self.Y_trains.append(Y_pred_train_avg)
        self.Y_tests.append(Y_pred_test_avg)
        # Return stats
        if method == 'auroc':
            import sklearn.metrics
            auc_train = sklearn.metrics.roc_auc_score(Y_train, Y_pred_train_avg)
            mcc_train = sklearn.metrics.matthews_corrcoef(Y_train, Y_pred_train_avg)
            if IX_test.shape[0] > 1:
                auc_test = sklearn.metrics.roc_auc_score(Y_test, Y_pred_test_avg)
                mcc_test = sklearn.metrics.roc_auc_score(Y_test, Y_pred_test_avg)
            else:
                auc_test = np.nan
                mcc_test = np.nan
            return auc_train, mcc_train, auc_test, mcc_test
        else:
            import scipy.stats
            rmse_train = (np.sum((Y_pred_train_avg-Y_train)**2)/Y_train.shape[0])**0.5
            rho_train = scipy.stats.pearsonr(Y_pred_train_avg, Y_train)[0]
            if IX_test.shape[0] > 0:
                rmse_test = (np.sum((Y_pred_test_avg-Y_test)**2)/Y_test.shape[0])**0.5
                rho_test = scipy.stats.pearsonr(Y_pred_test_avg, Y_test)[0]
            else:
                rmse_test = np.nan
                rho_test = np.nan
            return rmse_train, rho_train, rmse_test, rho_test
    def applyLatest(self, IX):
        regressor = self.regressors[-1]
        Y_pred = []
        if IX.shape[0] > 0:
            Y_pred = regressor.predict(IX)
        if type(Y_pred) == tuple:
            Y_pred_avg = Y_pred[0]
            Y_pred_std = Y_pred[1]
        else:
            Y_pred_avg = Y_pred
            Y_pred_std = np.zeros(len(Y_pred))
        #if len(Y_pred.shape) < 2:
        #    Y_pred = Y_pred.reshape((1,-1))
        #Y_pred_avg = np.median(Y_pred, axis=0)
        #Y_pred_std = np.std(Y_pred, axis=0)
        return Y_pred_avg, Y_pred_std
    def write(self, trunc='pred_i%d', log=None):
        iterations = sorted(self.iteration_preds)
        outfile_test = trunc+'_test.txt'
        outfile_train = trunc+'_train.txt'
        for it in iterations:
            # Training predictions
            preds_train = np.concatenate(self.iteration_train_preds[it], axis=0)
            trues_train = np.concatenate(self.iteration_train_trues[it], axis=0)
            np.savetxt(outfile_train % it, np.concatenate([preds_train, trues_train], axis=1))
            # Test predictions
            if len(self.iteration_preds[it]) > 0:
                preds_test = np.concatenate(self.iteration_preds[it], axis=0)
                trues_test = np.concatenate(self.iteration_trues[it], axis=0)
                np.savetxt(outfile_test % it, np.concatenate([preds_test, trues_test], axis=1))
            else:
                preds_test = []
                trues_test = []
                np.savetxt(outfile_test % it, np.array([]))
        return preds_train, trues_train, preds_test, trues_test
