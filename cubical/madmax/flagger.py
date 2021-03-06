import numpy as np
import os, os.path
import traceback
from cubical.tools import logger, ModColor
from cubical.flagging import FL
from cubical.statistics import SolverStats
from cubical.tools import BREAK  # useful: can set static breakpoints by putting BREAK() in the code
from cubical.madmax import plots

log = logger.getLogger("madmax")


# Conversion factor for sigma = SIGMA_MAD*mad
SIGMA_MAD = 1.4826

import __builtin__
try:
    __builtin__.profile
except AttributeError:
    # No line profiler, provide a pass-through version
    def profile(func): return func
    __builtin__.profile = profile 
    

class Flagger(object):
    def __init__(self, GD, chunk_label, metadata, stats):
        self.GD = GD
        self.metadata = metadata
        self.stats = stats
        self.chunk_label = chunk_label

        self.flag_warning_threshold = GD['flags']["warn-thr"]

        self._mode = GD['madmax']['enable']
        self._pretend = self._mode == "pretend"
        self.trial_mode = self._trial = self._mode == "trial"
        if self._pretend:
            self.desc_mode = "Pretend-Mad Max"
        elif self._mode == "trial":
            self.desc_mode = "Trial-Mad Max"
        elif self._mode:
            self.desc_mode = "Mad Max"
        else:
            self.desc_mode = "No Max"

        self.flagbit = 0 if self._pretend else FL.MAD

        self.mad_threshold = GD['madmax']['threshold']
        self.medmad_threshold = GD['madmax']['global-threshold']
        if not isinstance(self.mad_threshold, list):
            self.mad_threshold = [self.mad_threshold]
        if not isinstance(self.medmad_threshold, list):
            self.medmad_threshold = [self.medmad_threshold]
        self.mad_diag = GD['madmax']['diag']
        self.mad_offdiag = self.metadata.num_corrs == 4 and GD['madmax']['offdiag']
        if not self.mad_diag and not self.mad_offdiag:
            self._mode = False

        # setup MAD estimation settings
        self.mad_per_corr = False
        if GD['madmax']['estimate'] == 'corr':
            self.mad_per_corr = True
            self.mad_estimate_diag, self.mad_estimate_offdiag = self.mad_diag, self.mad_offdiag
        elif GD['madmax']['estimate'] == 'all':
            self.mad_estimate_diag = True
            self.mad_estimate_offdiag = self.metadata.num_corrs == 4
        elif GD['madmax']['estimate'] == 'diag':
            self.mad_estimate_diag, self.mad_estimate_offdiag = True, False
        elif GD['madmax']['estimate'] == 'offdiag':
            if self.metadata.num_corrs == 4:
                self.mad_estimate_diag, self.mad_estimate_offdiag = False, True
            else:
                self.mad_estimate_diag, self.mad_estimate_offdiag = True, False
        else:
            raise RuntimeError("invalid --madmax-estimate {} setting".format(GD['madmax']['estimate']))

        self._plotnum = 0

    def get_mad_thresholds(self):
        """MAD thresholds above are either a list, or empty. Each time we access the list, we pop the first element,
        until the list is down to one element."""
        if not self._mode:
            return 0, 0
        return self.mad_threshold.pop(0) if len(self.mad_threshold) > 1 else \
                   (self.mad_threshold[0] if self.mad_threshold else 0), \
               self.medmad_threshold.pop(0) if len(self.medmad_threshold) > 1 else \
                   (self.medmad_threshold[0] if self.medmad_threshold else 0)

    def get_plot_filename(self, kind=''):
        plotdir = '{}-madmax.plots'.format(self.GD['out']['name'])
        if not os.path.exists(plotdir):
            try:
                os.mkdir(plotdir)
            # allow a failure -- perhaps two workers got unlucky and both are trying to make the
            # same directory. Let savefig() below fail instead
            except OSError:
                pass
        if kind:
            filename = '{}/{}.{}.{}.png'.format(plotdir, self.chunk_label, self._plotnum, kind)
        else:
            filename = '{}/{}.{}.png'.format(plotdir, self.chunk_label, self._plotnum)
        self._plotnum += 1
        return filename

    @profile
    def report_carnage(self, absres, mad, baddies, flags_arr, method, max_label):
        made_plots = False
        n_tim, n_fre, n_ant, n_ant = baddies.shape
        nbad = int(baddies.sum())
        self.stats.chunk.num_mad_flagged += nbad

        if nbad:
            if nbad < flags_arr.size * self.flag_warning_threshold:
                warning, color = "", "blue"
            else:
                warning, color = "WARNING: ", "red"
            frac = nbad / float(baddies.size)
            mode = "trial-" if self._trial else ("pretend-" if self._pretend else "")
            print>> log(1, color), \
                "{warning}{max_label} {method} {mode}flags {nbad} ({frac:.2%}) visibilities".format(**locals())
            if log.verbosity() > 2 or self.GD['madmax']['plot']:
                per_bl = []
                total_elements = float(n_tim * n_fre)
                interesting_fraction = self.GD['madmax']['plot-frac-above']*total_elements
                plot_explicit_baseline = None
                for p in xrange(n_ant):
                    for q in xrange(p + 1, n_ant):
                        n_flagged = baddies[:, :, p, q].sum()
                        if n_flagged and n_flagged >= interesting_fraction:
                            per_bl.append((n_flagged, p, q))
                        if self.GD['madmax']['plot-bl'] == self.metadata.baseline_name[p,q]:
                            plot_explicit_baseline = (n_flagged, p ,q)
                per_bl = sorted(per_bl, reverse=True)
                # print
                per_bl_str = ["{} ({}m): {} ({:.2%})".format(self.metadata.baseline_name[p,q],
                                int(self.metadata.baseline_length[p,q]), n_flagged, n_flagged/total_elements)
                              for n_flagged, p, q in per_bl]
                print>> log(3), "{} of which per baseline: {}".format(max_label, ", ".join(per_bl_str))
                # plot, if asked to
                if self.GD['madmax']['plot']:
                    baselines_to_plot = []
                    if len(per_bl):
                        baselines_to_plot.append((per_bl[0], "worst baseline"))
                    if len(per_bl)>2:
                        baselines_to_plot.append((per_bl[len(per_bl)//2], "median baseline"))
                    if plot_explicit_baseline:
                        baselines_to_plot.append((plot_explicit_baseline,"--madmax-plot-bl"))
                    import pylab
                    for (n_flagged, p, q), baseline_label in baselines_to_plot:
                        # make subplots
                        subplot_titles = {}
                        for c1,x1 in enumerate(self.metadata.feeds.upper()):
                            for c2,x2 in enumerate(self.metadata.feeds.upper()):
                                mm = mad[0,p,q,c1,c2] if self.mad_per_corr else mad[0,p,q]
                                subplot_titles[c1,c2] = "{}{} residuals (MAD {:.2f})".format(x1, x2, mm)
                        figure = plots.make_dual_absres_plot(absres, flags_arr!=0, baddies, p, q, self.metadata, subplot_titles)
                        # make plot title with some info
                        fraction = n_flagged / total_elements
                        blname = self.metadata.baseline_name[p,q]
                        bllen  = int(self.metadata.baseline_length[p,q])
                        pylab.suptitle("{} {}: baseline {} ({}m), {} ({:.2%}) visibilities killed ({})".format(max_label,
                                        method, blname, bllen, n_flagged, fraction, baseline_label))
                        # save or show plot
                        if self.GD['madmax']['plot'] == 'show':
                            pylab.show()
                        else:
                            filename = self.get_plot_filename()
                            figure.savefig(filename, dpi=300)
                            print>>log(1),"{}: saving Mad Max flagging plot to {}".format(self.chunk_label,filename)
                        pylab.close(figure)
                        del figure
                        made_plots = True
        else:
            print>> log(2),"{} {} abides".format(max_label, method)
        return made_plots


    @profile
    def beyond_thunderdome(self, resid_arr, data_arr, model_arr, flags_arr, threshold, med_threshold, max_label):
        """This function implements MAD-based flagging on residuals"""
        if not threshold and not med_threshold:
            return False
        n_mod, _, _, n_ant, n_ant, n_cor, n_cor = resid_arr.shape

        import cubical.kernels
        cymadmax = cubical.kernels.import_kernel("cymadmax")
        # estimate MAD of off-diagonal elements
        absres = np.empty_like(resid_arr, dtype=np.float32)
        np.abs(resid_arr, out=absres)
        if self.mad_per_corr:
            mad, goodies = cymadmax.compute_mad_per_corr(absres, flags_arr, diag=self.mad_estimate_diag, offdiag=self.mad_estimate_offdiag)
        else:
            mad, goodies = cymadmax.compute_mad(absres, flags_arr, diag=self.mad_estimate_diag, offdiag=self.mad_estimate_offdiag)
        # any of it non-zero?
        if mad.mask.all():
            return
        # estimate median MAD
        medmad = np.ma.median(mad, axis=(1,2))
        # all this was worth it, just so I could type "mad.max()" as legit code
        print>>log(2),"{} per-baseline MAD min {:.2f}, max {:.2f}, median {:.2f}".format(max_label, mad.min(), mad.max(), np.ma.median(medmad))
        if log.verbosity() > 4:
            for imod in xrange(n_mod):
                if self.mad_per_corr:
                    for ic1,c1 in enumerate(self.metadata.feeds):
                        for ic2,c2 in enumerate(self.metadata.feeds):
                            per_bl = [(mad[imod,p,q,ic1,ic2], p, q) for p in xrange(n_ant)
                                      for q in xrange(p+1, n_ant) if not mad.mask[imod,p,q,ic1,ic2]]
                            per_bl = ["{} ({}m): {:.2f}".format(self.metadata.baseline_name[p,q], int(self.metadata.baseline_length[p,q]), x)
                                      for x, p, q in sorted(per_bl)[::-1]]
                            print>>log(4),"{} model {} {}{} MADs are {}".format(max_label, imod,
                                                                                c1.upper(), c2.upper(), ", ".join(per_bl))
                else:
                    per_bl = [(mad[imod,p,q,], p, q) for p in xrange(n_ant)
                              for q in xrange(p+1, n_ant) if not mad.mask[imod,p,q]]
                    per_bl = ["{} ({}m) {:.2f}".format(self.metadata.baseline_name[p,q], int(self.metadata.baseline_length[p,q]), x)
                              for x, p, q in sorted(per_bl)[::-1]]
                    print>>log(4),"{} model {} MADs are {}".format(max_label, imod, ", ".join(per_bl))


        made_plots = False
        thr = np.zeros((n_mod, n_ant, n_ant, n_cor, n_cor), dtype=np.float32)
        # apply per-baseline MAD threshold
        if threshold:
            if self.mad_per_corr:
                thr[:] = threshold * mad / SIGMA_MAD
            else:
                thr[:] = threshold * mad[...,np.newaxis,np.newaxis] / SIGMA_MAD
            baddies = cymadmax.threshold_mad(absres, thr, flags_arr, self.flagbit, goodies,
                                             diag=self.mad_diag, offdiag=self.mad_offdiag)
            made_plots = self.report_carnage(absres, mad, baddies, flags_arr,
                                                "baseline-based Mad Max ({} sigma)".format(threshold), max_label)
            if not self._pretend:
                baddies = baddies.astype(bool)
                model_arr[:,:,baddies,:,:] = 0
                data_arr[:,baddies,:,:] = 0

        # apply global median MAD threshold
        if med_threshold:
            med_thr = med_threshold * medmad / SIGMA_MAD
            if self.mad_per_corr:
                thr[:] = med_thr[:,np.newaxis,np.newaxis,:,:]
            else:
                thr[:] = med_thr[:,np.newaxis,np.newaxis,np.newaxis,np.newaxis]
            baddies = cymadmax.threshold_mad(absres, thr, flags_arr, self.flagbit, goodies,
                                             diag=self.mad_diag, offdiag=self.mad_offdiag)
            made_plots = made_plots or \
                self.report_carnage(absres, mad, baddies, flags_arr,
                                       "global Mad Max ({} sigma)".format(med_threshold), max_label)
            if not self._pretend:
                baddies = baddies.astype(bool)
                model_arr[:, :, baddies, :, :] = 0
                data_arr[:, baddies, :, :] = 0
        else:
            med_thr = None

        # generate overview plot
        if made_plots:
            import pylab
            outflags, figure = plots.make_baseline_mad_plot(mad, medmad, med_thr, metadata=self.metadata,
                                max_label=max_label,
                                antenna_mad_threshold=self.GD['madmax']['flag-ant-thr'])
            if outflags.any():
                if self.mad_per_corr:
                    outflags = outflags.any(axis=(-1,-2))
                if self.GD['madmax']['flag-ant'] and not self._pretend:
                    print>>log(0, "red"),"{} baselines {}flagged on mad residuals (--madmax-flag-ant 1)".format(
                                            outflags.sum()/2, "trial-" if self._trial else "")
                    flags_arr[:,:,outflags] |= self.flagbit
                    model_arr[:,:,:,:,outflags,:,:] = 0
                    data_arr[:,:,:,outflags,:,:] = 0
                else:
                    print>>log(0, "red"),"{} baselines would have been flagged due to mad residuals (use --madmax-flag-ant)".format(outflags.sum()/2)

            if self.GD['madmax']['plot'] == 'show':
                pylab.show()
            else:
                filename = self.get_plot_filename('mads')
                print>>log(1),"{}: saving MAD distribution plot to {}".format(self.chunk_label,filename)
                figure.savefig(filename, dpi=300)
                import cPickle
                pickle_file = filename+".cp"
                cPickle.dump((mad, medmad, med_thr, self.metadata, max_label), open(pickle_file, "w"), 2)
                print>>log(1),"{}: pickling MAD distribution to {}".format(self.chunk_label, pickle_file)
            pylab.close(figure)
            del figure
