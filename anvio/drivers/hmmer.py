# coding: utf-8
"""Interface to HMMer."""

import os
import gzip
import shutil

import anvio
import anvio.utils as utils
import anvio.terminal as terminal
import anvio.filesnpaths as filesnpaths

from anvio.errors import ConfigError


__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2018, the Meren Lab (http://merenlab.org/)"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "A. Murat Eren"
__email__ = "a.murat.eren@gmail.com"


run = terminal.Run()
progress = terminal.Progress()
pp = terminal.pretty_print


class HMMer:
    def __init__(self, target_files_dict, num_threads_to_use=1, progress=progress, run=run):
        """A class to streamline HMM runs."""
        self.num_threads_to_use = num_threads_to_use
        self.progress = progress
        self.run = run

        self.target_files_dict = target_files_dict

        # hmm_scan_hits is the file to access later on for parsing:
        self.hmm_scan_output = None
        self.hmm_scan_hits = None
        self.genes_in_contigs = None

        self.tmp_dirs = []


    def run_hmmscan(self, source, alphabet, context, kind, domain, num_genes_in_model, hmm, ref, noise_cutoff_terms):
        target = ':'.join([alphabet, context])

        if target not in self.target_files_dict:
            raise ConfigError("You have an unknown target :/ Target, which defines an alphabet and context\
                                to clarify whether the HMM search is supposed to be done using alphabets DNA,\
                                RNA, or AA sequences, and contexts of GENEs or CONTIGs. Yours is %s, and it\
                                doesn't work for anvi'o." % target)

        if not self.target_files_dict[target]:
            raise ConfigError("HMMer class does not know about Sequences file for the target %s :/" % target)

        self.run.warning('', header='HMM Profiling for %s' % source, lc='green')
        self.run.info('Reference', ref if ref else 'unknown')
        self.run.info('Kind', kind if kind else 'unknown')
        self.run.info('Alphabet', alphabet)
        self.run.info('Context', context)
        self.run.info('Domain', domain if domain else 'N\\A')
        self.run.info('HMM model path', hmm)
        self.run.info('Number of genes', num_genes_in_model)
        self.run.info('Noise cutoff term(s)', noise_cutoff_terms)
        self.run.info('Number of CPUs will be used for search', self.num_threads_to_use)

        tmp_dir = filesnpaths.get_temp_directory_path()
        self.tmp_dirs.append(tmp_dir)

        self.hmm_scan_output = os.path.join(tmp_dir, 'hmm.output')
        self.hmm_scan_hits = os.path.join(tmp_dir, 'hmm.hits')
        self.hmm_scan_hits_shitty = os.path.join(tmp_dir, 'hmm.hits.shitty')
        log_file_path = os.path.join(tmp_dir, '00_log.txt')

        self.run.info('Temporary work dir', tmp_dir)
        self.run.info('HMM scan output', self.hmm_scan_output)
        self.run.info('HMM scan hits', self.hmm_scan_hits)
        self.run.info('Log file', log_file_path)

        self.progress.new('Unpacking the model into temporary work directory')
        self.progress.update('...')
        hmm_file_path = os.path.join(tmp_dir, 'hmm.txt')
        hmm_file = open(hmm_file_path, 'wb')
        hmm_file.write(gzip.open(hmm, 'rb').read())
        hmm_file.close()
        self.progress.end()

        self.progress.new('Processing')
        self.progress.update('Compressing the pfam model')

        cmd_line = ['hmmpress', hmm_file_path]
        ret_val = utils.run_command(cmd_line, log_file_path)

        if ret_val:
            raise ConfigError("The last call did not work quite well. Most probably the version of HMMER you have\
                               installed is either not up-to-date enough, or too new :/ Just to make sure what went\
                               wrong please take a look at the log file ('%s'). Please visit %s to see what\
                               is the latest version availalbe if you think updating HMMER can resolve it. You can\
                               learn which version of HMMER you have on your system by typing 'hmmpress -h'."\
                                       % (log_file_path, 'http://hmmer.janelia.org/download.html'))
        self.progress.end()

        self.progress.new('Processing')
        self.progress.update('Performing HMM scan ...')

        cmd_line = ['nhmmscan' if alphabet in ['DNA', 'RNA'] else 'hmmscan',
                    '-o', self.hmm_scan_output, *noise_cutoff_terms.split(),
                    '--cpu', self.num_threads_to_use,
                    '--tblout', self.hmm_scan_hits_shitty,
                    hmm_file_path, self.target_files_dict[target]]

        utils.run_command(cmd_line, log_file_path)

        if not os.path.exists(self.hmm_scan_hits_shitty):
            self.progress.end()
            raise ConfigError("Something went wrong with hmmscan, and it failed to generate the\
                                expected output :/ Fortunately, this log file should tell you what\
                                might be the problem: '%s'. Please do not forget to include this\
                                file if you were to ask for help." % log_file_path)

        self.progress.end()

        # thank you, hmmscan, for not generating a simple TAB-delimited, because we programmers
        # love to write little hacks like this into our code:
        parseable_output = open(self.hmm_scan_hits, 'w')
        
        detected_non_ascii = False
        lines_with_non_ascii = []

        with open(self.hmm_scan_hits_shitty, 'rb') as hmm_hits_file:
            line_counter = 0
            for line_bytes in hmm_hits_file:
                line_counter += 1
                line = line_bytes.decode('ascii', 'ignore')

                if not len(line) == len(line_bytes):
                    lines_with_non_ascii.append(line_counter)
                    detected_non_ascii = True

                if line.startswith('#'):
                    continue
            
                parseable_output.write('\t'.join(line.split()[0:18]) + '\n')
        
        parseable_output.close()

        if detected_non_ascii:
            self.run.warning("Just a heads-up, Anvi'o HMMer parser detected non-ascii charachters while processing \
                the file '%s' and cleared them. Here are the line numbers with non-ascii charachters: %s.\
                You may want to check those lines with a command like \"awk 'NR==<line number>' <file path> | cat -vte\"." % 
                (self.hmm_scan_hits_shitty, ", ".join(map(str, lines_with_non_ascii))))

        num_raw_hits = filesnpaths.get_num_lines_in_file(self.hmm_scan_hits)
        self.run.info('Number of raw hits', num_raw_hits)

        return self.hmm_scan_hits if num_raw_hits else None


    def clean_tmp_dirs(self):
        for tmp_dir in self.tmp_dirs:
            shutil.rmtree(tmp_dir)


