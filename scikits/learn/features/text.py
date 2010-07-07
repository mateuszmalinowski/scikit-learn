# Author: Olivier Grisel <olivier.grisel@ensta.org>
#
# License: BSD Style.
"""Utilities to build feature vectors from text documents"""

import re
import unicodedata
import numpy as np


def strip_accents(s):
    """Transform accentuated unicode symbols into their simple counterpart"""
    return ''.join((c for c in unicodedata.normalize('NFD', s)
                    if unicodedata.category(c) != 'Mn'))


class SimpleAnalyzer(object):
    """Simple analyzer: transform a text document into a sequence of tokens

    This simple implementation does:
        - lower case conversion
        - unicode accents removal
        - token extraction using unicode regexp word bounderies for token of
          minimum size of 2 symbols
    """

    token_pattern = re.compile(r"\b\w\w+\b", re.U)

    # TODO: make it possible to pass stop words list here

    def __init__(self, default_charset='utf-8'):
        self.charset = default_charset

    def analyze(self, text_document):
        if isinstance(text_document, str):
            text_document = text_document.decode(self.charset, 'ignore')
        text_document = strip_accents(text_document.lower())
        return self.token_pattern.findall(text_document)


class HashingVectorizer(object):
    """Compute term frequencies vectors using hashed term space

    See the Hashing-trick related papers referenced by John Langford on this
    page to get a grasp on the usefulness of this representation:

      http://hunch.net/~jl/projects/hash_reps/index.html

    dim is the number of buckets, higher dim means lower collision rate but
    also higher memory requirements and higher processing times on the
    resulting tfidf vectors.

    Documents is a sequence of lists of tokens to initialize the DF estimates.

    TODO handle bigrams in a smart way such as demonstrated here:

      http://streamhacker.com/2010/05/24/text-classification-sentiment-analysis-stopwords-collocations/

    """
    # TODO: implement me using the murmurhash that might be faster: but profile
    # me first :)

    # TODO: make it possible to select between the current dense representation
    # and sparse alternatives from scipy.sparse once the liblinear and libsvm
    # wrappers have been updated to be able to handle it efficiently

    def __init__(self, dim=5000, probes=3, analyzer=SimpleAnalyzer(),
                 use_idf=True):
        self.dim = dim
        self.probes = probes
        self.analyzer = analyzer
        self.use_idf = use_idf

        # start counts at one to avoid zero division while
        # computing IDF
        self.df_counts = np.ones(dim, dtype=long)
        self.tf_vectors = None
        self.sampled = 0

    def hash_sign(self, token, probe=0):
        h = hash(token + (probe * u"#"))
        return abs(h) % self.dim, 1.0 if h % 2 == 0 else -1.0

    def sample_document(self, text, tf_vector=None, update_estimates=True):
        """Extract features from text and update running freq estimates"""
        if tf_vector is None:
            # allocate term frequency vector and stack to history
            tf_vector = np.zeros(self.dim, np.float64)
            if self.tf_vectors is None:
                self.tf_vectors = tf_vector.reshape((1, self.dim))
            else:
                self.tf_vectors = np.vstack((self.tf_vectors, tf_vector))
                tf_vector = self.tf_vectors[-1]

        tokens = self.analyzer.analyze(text)
        for token in tokens:
            # TODO add support for cooccurence tokens in a sentence
            # window
            for probe in xrange(self.probes):
                i, incr = self.hash_sign(token, probe)
                tf_vector[i] += incr
        tf_vector /= len(tokens) * self.probes

        if update_estimates and self.use_idf:
            # update the running DF estimate
            self.df_counts += tf_vector != 0.0
            self.sampled += 1
        return tf_vector

    def get_idf(self):
        return np.log(float(self.sampled) / self.df_counts)

    def get_tfidf(self):
        """Compute the TF-log(IDF) vectors of the sampled documents"""
        if self.tf_vectors is None:
            return None
        return self.tf_vectors * self.get_idf()

    def vectorize(self, document_filepaths):
        """Vectorize a batch of documents"""
        tf_vectors = np.zeros((len(document_filepaths), self.dim))
        for i, filepath in enumerate(document_filepaths):
            self.sample_document(file(filepath).read(), tf_vectors[i])

        if self.tf_vectors is None:
            self.tf_vectors = tf_vectors
        else:
            self.tf_vectors = np.vstack((self.tf_vectors, tf_vectors))

    def get_vectors(self):
        if self.use_idf:
            return self.get_tfidf()
        else:
            return self.tf_vectors

