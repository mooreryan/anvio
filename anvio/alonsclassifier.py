# -*- coding: utf-8
# pylint: disable=line-too-long
"""
    Classes to classify genes based on coverages across metagenomes.

    anvi-alons-classifier is the default client using this module
"""

import numpy as np

import anvio
import anvio.utils as utils
import anvio.terminal as terminal

from anvio.errors import ConfigError


__author__ = "Alon Shaiber"
__copyright__ = "Copyright 2017, The anvio Project"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Alon Shaiber"
__email__ = "alon.shaiber@gmail.com"


run = terminal.Run()
progress = terminal.Progress()
pp = terminal.pretty_print


class AlonsClassifier:
    def __init__(self, args, run=run, progress=progress):
        self.run = run
        self.progress = progress

        A = lambda x: args.__dict__[x] if x in args.__dict__ else None
        self.data_file_path = A('data_file')
        self.output = A('output')
        self.sample_detection_output = A('sample_detection_output')
        self.alpha = A('alpha')
        self.beta = A('beta')
        self.gamma = A('gamma')
        self.eta = A('eta')
        self.additional_layers_to_append = A('additional_layers_to_append')
        self.samples_information_to_append = A('samples_information_to_append')


    def sanity_check(self):
        """Basic sanity check for class inputs"""
        if not isinstance(self.gamma, float):
            raise ConfigError("Gamma value must be a type float.")


    def get_data_from_txt_file(self):
        """ Reads the coverage data from TAB delimited file """
        samples = utils.get_columns_of_TAB_delim_file(self.data_file_path)
        data = utils.get_TAB_delimited_file_as_dictionary(self.data_file_path, column_mapping=[int] + [float] * len(samples))
        return data, samples


    def apply_func_to_genes_in_sample(self, data, samples, func, list_of_genes=None):
        """ Apply the give function on the list of genes in each sample. The function is expected to accept a list """
        if not list_of_genes:
            list_of_genes = data.keys()
        d = dict(zip(samples, [next(map(func, [[data[gene_id][sample_id] for gene_id in list_of_genes]])) for
                           sample_id in samples]))
        return d


    def get_mean_coverage_in_samples(self, data, samples, list_of_genes=None):
        """ Returns a dictionary with of the average coverage value of the list of genes per sample. if no list of genes is
        supplied then the average is calculated over all genes """
        if not samples:
            # if all samples don't contain the genome then return 0 for mean value
            return 0
        else:
            mean_coverage_in_samples = self.apply_func_to_genes_in_sample(data, samples, np.mean, list_of_genes)
            return mean_coverage_in_samples


    def get_std_in_samples(self, data, samples, list_of_genes=None):
        """ Returns a dictionary with of the standard deviation of the coverage values of the list of genes per sample.
        if no list of genes is supplied then the average is calculated over all genes """
        std_in_samples = self.apply_func_to_genes_in_sample(data, samples, np.std, list_of_genes)
        return std_in_samples


    def get_detection_of_genes(self, data, samples, mean_coverage_in_samples, std_in_samples, gamma):
        """ Returns a dictionary (of dictionaries), where for each gene_id, and each sample_id the detection of the gene
        is determined. The criteria for detection is having coverage that is greater than 0 and also that is not more
        than 3 (assuming gamma=3 for example) standard deviations below the mean coverage in the sample.
        Notice that the mean coverage isn't the mean of all genes in the sample necesarilly. In fact it would be the mean of
        only the taxon-specific genes."""
        detection_of_genes = {}
        non_zero_non_detections = False
        for gene_id in data:
            detection_of_genes[gene_id] = {}
            detection_of_genes[gene_id]['number_of_detections'] = 0
            for sample in samples:
                detection_of_genes[gene_id][sample] = data[gene_id][sample] > max(0,mean_coverage_in_samples[sample] -
                                                                                 gamma*std_in_samples[sample])
                detection_of_genes[gene_id]['number_of_detections'] += detection_of_genes[gene_id][sample]
                if data[gene_id][sample] > 0 and data[gene_id][sample] < mean_coverage_in_samples[sample] - \
                        gamma*std_in_samples[sample]:
                    non_zero_non_detections = True
        if non_zero_non_detections:
            # print('gene %s, in some sample has non-zero coverage %s, and it has been marked as not detected due '
                  # 'to the detection criteria' % (gene_id, data[gene_id][sample]))
                  print('some genes in some samples were marked as not detected due to the detection criteria')
        return detection_of_genes


    def get_detection_of_genome_in_samples(self, detection_of_genes, samples, alpha, genes_to_consider=None):
        if not genes_to_consider:
            # if no list of genes is supplied then considering all genes
            genes_to_consider = detection_of_genes.keys()
        detection_of_genome_in_samples = {}
        for sample_id in samples:
            detection_of_genome_in_samples[sample_id] = {}
            number_of_detected_genes_in_sample = len([gene_id for gene_id in genes_to_consider if detection_of_genes[
                gene_id][sample_id]])
            detection_of_genome_in_samples[sample_id]['detection'] = number_of_detected_genes_in_sample > alpha * len(
                genes_to_consider)
        return detection_of_genome_in_samples


    def get_adjusted_std_for_gene_id(self, data, gene_id, samples, mean_coverage_in_samples, detection_of_genes):
        """Returns the adjusted standard deviation for a gene_id """
        # Note: originally I thought I would only consider samples in which the genome was detected, but in fact,
        # if a gene is detected in a sample in which the genome is not detected then that is a good sign that this is
        #  a TNS gene. But I still kept here the original definition of adjusted_std
        # adjusted_std = np.std([d[gene_id, sample_id] / mean_coverage_in_samples[sample_id] for sample_id in samples if (
        #         detection_of_genes[gene_id][sample_id] and detection_of_genome_in_samples[sample_id])])
        if samples == []:
            return 0
        else:
            samples_with_gene = []
            for sample_id in samples:
                if detection_of_genes[gene_id][sample_id] and mean_coverage_in_samples[sample_id]>0:
                    samples_with_gene.append(sample_id)
            if not samples_with_gene:
                return 0
            else:
                adjusted_std = np.std([data[gene_id][sample_id]/mean_coverage_in_samples[sample_id] for sample_id in
                                       samples_with_gene])
                return adjusted_std


    def get_adjusted_stds(self, data, samples, mean_coverage_in_samples, detection_of_genes):
        adjusted_std = {}
        for gene_id in data:
            adjusted_std[gene_id] = self.get_adjusted_std_for_gene_id(data, gene_id, samples, mean_coverage_in_samples,
                                                                 detection_of_genes)
        return adjusted_std


    def get_taxon_specificity(self, adjusted_stds, detection_of_genes, beta):
        """For each gene if the adjusted standard deviation (to understand what this is refer to Alon Shaiber) is smaller
        than beta the the gene is a taxon-specific gene (TS), otherwise, it is a non-taxon-specific gene (TNS)"""
        taxon_specificity = {}

        for gene_id in adjusted_stds:
            # if the gene is not detected in any sample then return NaN
            if detection_of_genes[gene_id]['number_of_detections'] <= 1:
                taxon_specificity[gene_id] = 'NaN'
            else:
                if adjusted_stds[gene_id] < beta:
                    taxon_specificity[gene_id] = 'TS'
                else:
                    taxon_specificity[gene_id] = 'TNS'
        return taxon_specificity


    def get_loss_function_value(self, taxon_specificity, adjusted_stds, beta):
        loss = 0
        for gene_id in taxon_specificity:
            if taxon_specificity[gene_id] == 'TS':
                # Notice: here adjusted std includes the samples that don't have the genome detected in them (it kind of
                # makes sense, because if the gene is detected even though the genome is not, then maybe it's not
                # taxon-specific
                loss += adjusted_stds[gene_id]
            else:
                loss += beta
        return loss


    def get_number_of_detections_for_gene(self, detection_of_genes, gene_id, samples):
        detections = 0
        for sample_id in samples:
            detections += detection_of_genes[gene_id][sample_id]
        return detections


    def get_core_accessory_info(self, detection_of_genes, gene_id, samples_with_genome, eta):
        """ Returns 'core'/'accessory' classification for each gene. This is done using only the samples in which the
        genome is detected """
        if detection_of_genes[gene_id]['number_of_detections'] == 0:
            return 'NaN'
        elif self.get_number_of_detections_for_gene(detection_of_genes, gene_id, samples_with_genome) < eta * len(
            samples_with_genome):
            return 'accessory'
        else:
            return 'core'


    def get_gene_class(self, taxon_specificity, core_or_accessory):
        if taxon_specificity == 'NaN' or core_or_accessory == 'NaN':
            return 'NaN'
        elif taxon_specificity == 'TS':
            if core_or_accessory == 'core':
                return 'TSC'
            elif core_or_accessory == 'accessory':
                return 'TSA'
            else:
                print('%s is not valid. Value should be \'core\' or \'accessory\'' % core_or_accessory)
                exit(1)
        elif taxon_specificity == 'TNS':
            if core_or_accessory == 'core':
                return 'TNC'
            elif core_or_accessory == 'accessory':
                return 'TNA'
            else:
                print('%s is not valid. Value should be \'core\' or \'accessory\'' % core_or_accessory)
                exit(1)
        else:
            print('%s is not valid. Value should be \'TS\' or \'TNS\'' % taxon_specificity)
            exit(1)

    def report_gene_class_information(self, gene_class_information,detection_of_genome_in_samples):
        C = lambda dictionary, field, value : len([dict_id for dict_id in dictionary if dictionary[
            dict_id][field]==value])
        number_of_TS = C(gene_class_information, 'gene_specificity','TS')
        number_of_TSC = C(gene_class_information, 'gene_class','TSC')
        number_of_TSA = C(gene_class_information, 'gene_class','TSA')
        number_of_TNC = C(gene_class_information, 'gene_class','TNC')
        number_of_TNA = C(gene_class_information, 'gene_class','TNA')
        number_of_NaN = C(gene_class_information, 'gene_class', None)
        number_of_positive_samples = C(detection_of_genome_in_samples, 'detection', True)

        print('The number of TS is %s' % number_of_TS )
        print('The number of TSC is %s' % number_of_TSC)
        print('The number of TSA is %s' % number_of_TSA)
        print('The number of TNC is %s' % number_of_TNC)
        print('The number of TNA is %s' % number_of_TNA)
        print('The number of NaN is %s' % number_of_NaN)
        print('The number of samples with the genome is %s' % number_of_positive_samples)


    def get_gene_classes(self, data, samples):
        """ returning the classification per gene along with detection in samples (i.e. for each sample, whether the
        genome has been detected in the sample or not """
        taxon_specific_genes = list(data.keys())
        converged = False
        loss = None
        TSC_genes = list(data.keys())

        gene_class_information = {}
        while not converged:
            # mean of coverage of all TS genes in each sample
            mean_coverage_of_TS_in_samples = self.get_mean_coverage_in_samples(data,samples,taxon_specific_genes)
            # Get the standard deviation of the taxon-specific genes in a sample
            # TODO: right now, single copy, and multi-copy genes would be treated identically. Hence, multi-copy genes
            # would skew both the mean and the std of the taxon-specific genes.
            std_of_TS_in_samples = self.get_std_in_samples(data, samples, taxon_specific_genes)
            detection_of_genes = self.get_detection_of_genes(data, samples, mean_coverage_of_TS_in_samples, std_of_TS_in_samples, self.gamma)
            detection_of_genome_in_samples = self.get_detection_of_genome_in_samples(detection_of_genes, samples, self.alpha, TSC_genes)
            samples_with_genome = [sample_id for sample_id in samples if detection_of_genome_in_samples[sample_id][
                'detection']]
            adjusted_stds = self.get_adjusted_stds(data,samples,mean_coverage_of_TS_in_samples,detection_of_genes)
            taxon_specificity = self.get_taxon_specificity(adjusted_stds, detection_of_genes, self.beta)
            new_loss = self.get_loss_function_value(taxon_specificity, adjusted_stds, self.beta)
            epsilon = 2 * self.beta
            if loss is not None:
                if abs(new_loss - loss) < epsilon:
                    converged = True
            loss = new_loss
            print('current value of loss function: %s ' % loss)

            for gene_id in data:
                gene_class_information[gene_id] = {}
                gene_class_information[gene_id]['gene_specificity'] = taxon_specificity[gene_id]
                gene_class_information[gene_id]['number_of_detections'] = detection_of_genes[gene_id]['number_of_detections']
                gene_class_information[gene_id]['core_or_accessory'] = self.get_core_accessory_info(detection_of_genes, gene_id,
                                                                                               samples_with_genome, self.eta)
                gene_class_information[gene_id]['gene_class'] = self.get_gene_class(gene_class_information[gene_id][
                                                   'gene_specificity'], gene_class_information[gene_id]['core_or_accessory'])
                # counting the number of positive samples that contain the gene
                gene_class_information[gene_id]['detection_in_positive_samples'] = len([sample_id for sample_id in
                                                                samples_with_genome if detection_of_genes[gene_id][sample_id]])
                # Getting the portion of positive samples that contain the gene
                if gene_class_information[gene_id]['detection_in_positive_samples'] == 0:
                    gene_class_information[gene_id]['portion_detected'] = 0
                else:
                    gene_class_information[gene_id]['portion_detected'] = gene_class_information[gene_id][
                        'detection_in_positive_samples'] / len(samples_with_genome)

            TSC_genes = [gene_id for gene_id in gene_class_information if gene_class_information[gene_id][
                'gene_class']=='TSC']
            # taxon_specific_genes = [gene_id for gene_id in gene_class_information if gene_class_information[gene_id][
            #     'gene_class']=='TSC' or gene_class_information[gene_id]['gene_class']=='TSA']
            self.report_gene_class_information(gene_class_information, detection_of_genome_in_samples)
        final_detection_of_genome_in_samples = self.get_detection_of_genome_in_samples(detection_of_genes, samples, self.alpha,
                                                                            genes_to_consider=TSC_genes)
        return gene_class_information, final_detection_of_genome_in_samples

    def get_specificity_from_class_id(self, class_id):
        try:
            class_id = int(class_id)
        except:
            raise ConfigError("Classes must be of type integer. You sent this: ", class_id)

        classes = {0: 'None',
                   1: 'TS',
                   2: 'TS',
                   3: 'TS',
                   4: 'TNS',
                   5: 'TNS'}

        try:
            return classes(class_id)
        except:
            raise ConfigError("The class id '%d' is not a valid one. Try one of these: '%s'" % (class_id, ', '.join(list(classes.keys()))))


    def classify(self):
        data, samples = self.get_data_from_txt_file()
        gene_class_information, detection_of_genome_in_samples = self.get_gene_classes(data, samples)
    
        if not self.additional_layers_to_append:
            additional_column_titles = []
            additional_layers_dict = gene_class_information
        else:
            additional_column_titles = utils.get_columns_of_TAB_delim_file(self.additional_layers_to_append)
            additional_layers_dict = utils.get_TAB_delimited_file_as_dictionary(self.additional_layers_to_append,
                                                                                dict_to_append=gene_class_information,
                                                                                assign_none_for_missing=True,
                                                                                column_mapping=[int]+[str]*len(additional_column_titles))
    
        utils.store_dict_as_TAB_delimited_file(additional_layers_dict, self.output, headers=['gene_callers_id',
                                                                                                       'gene_class',
                                                                                                       'number_of_detections', 'portion_detected'] + additional_column_titles)
        if not self.samples_information_to_append:
            samples_information_column_titles = []
            samples_information_dict = detection_of_genome_in_samples
        else:
            samples_information_column_titles = utils.get_columns_of_TAB_delim_file(self.samples_information_to_append)
            samples_information_dict = utils.get_TAB_delimited_file_as_dictionary(self.samples_information_to_append,
                                                                                dict_to_append=detection_of_genome_in_samples,
                                                                                assign_none_for_missing=True,
                                                                                column_mapping=[str]+[str]*len(
                                                                                    samples_information_column_titles))
        utils.store_dict_as_TAB_delimited_file(samples_information_dict, self.sample_detection_output,
                                                   headers=['samples','detection'] + samples_information_column_titles)


