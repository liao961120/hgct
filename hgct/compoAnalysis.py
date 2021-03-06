#%%
from itertools import chain
from collections import Counter
from CompoTree import ComponentTree, Radicals, IDC
from CompoTree import CTFounds
from .UtilsGeneral import PAT_CH_CHR

ctree = ComponentTree.load()
radicals = Radicals.load()
idc_names = { x.name for x in IDC }

class CompoAnalysis:

    def __init__(self, corpus_reader):
        """[summary]

        Parameters
        ----------
        IndexedCorpus : IndexedCorpus
            A corpus with an index of character positions. Accepts 
            :class:`dcctk.corpus.IndexedCorpus` or its super classes as inputs.
        """
        self.corpus_reader = corpus_reader
        self.n_subcorp = corpus_reader.n_subcorp
        self.cc_map = {}
        self.rad_map = {}
        self.idc_map = {}
        self.fq_distr_cache = {}
        self.corp_fq_info = {}
        self.chars = set(self.freq_distr(tp="chr").keys())
        self._build_cc_map()
        self._build_rad_map()
        self._build_idc_map()


    @property
    def corpus(self):
        """Return a corpus as a generator
        """
        return self.corpus_reader.get_corpus_as_gen()


    def productivity(self, radical=None, compo=None, idc=None, pos=-1, 
                     subcorp_idx:int=None, text_idx:int=None):

        chr_fq = self.freq_distr(subcorp_idx, text_idx, "chr")
        if isinstance(radical, str):
            chars = self.rad_map.get(radical, set())
        elif isinstance(compo, str):
            chars = self._component_search(compo, idc, pos)
        elif isinstance(idc, str):
            chars = self._idc_search(idc)
        else:
            raise Exception("One of `radical`, `compo`, or `idc` must be given")
        chars.intersection_update(chr_fq.keys())

        V1C, NC = 0, 0
        for ch in chars:
            fq = chr_fq[ch]
            NC += fq
            if fq == 1: V1C += 1
        
        # Static info
        k = (subcorp_idx, text_idx)
        if k not in self.corp_fq_info:
            self.corp_fq_info[k] = {
                'N': sum(chr_fq.values()),
                'V1': sum(f for f in chr_fq.values() if f == 1)
            }

        V1 = self.corp_fq_info[k]['V1']
        return {
            'productivity': {
                'realized': len(chars),
                'expanding': V1C / V1,
                'potential': V1C / NC if V1C != 0 else 0,
            },
            'N': self.corp_fq_info[k]['N'],
            'V1': V1,
            'V1C': V1C,
            'NC': NC
        }

    def _component_search(self, compo:str, idc=None, pos:int=-1):
        bottom_hits = ctree.find(compo, max_depth=1, bmp_only=True)
        if idc is None:
            return set( x[0] for x in CTFounds(bottom_hits)\
                .tolist() )
        return set( x[0] for x in CTFounds(bottom_hits)\
            .filter(idc=IDC[idc].value, pos=pos)\
            .tolist() )

    
    def _idc_search(self, idc:str="vert2"):
        if idc == "" or idc.upper() == "NULL":
            return self.idc_map.get("NULL")
        global idc_names
        if idc not in idc_names: 
            raise Exception(f"Invalid IDC value `{idc}`!", 
                            f"IDC must be one of {', '.join(idc_names)}")
        return self.idc_map.get(idc, set())



    def freq_distr(self, subcorp_idx=None, text_idx=None,
                   tp="chr", use_chr_types=False,
                   compo=None, idc=None, pos=-1, radical=None, 
                   prob=False, per_n_tk=1, chinese_only=True):
        """Frequency distribution of character (component/feature)

        Parameters
        ----------
        subcorp_idx : int, optional
            Index for subcorpus, by default None, which uses the whole corpus.
        text_idx : int, optional
            Index for text in a subcorpus, by default None, which uses the 
            whole subcorpus.
        tp : str, optional
            One of :code:`chr` (Character), :code:`idc` 
            (Ideographic Description Characters), :code:`rad` (Radical), 
            and None (Comonent Search), by default :code:`idc`

        Returns
        -------
        Counter
            A freqeuncy distribution.
        """
        # Use cache (only for character distribution)
        k = (subcorp_idx, text_idx, tp, compo, idc, pos, radical, chinese_only)
        if k in self.fq_distr_cache: return normalize(self.fq_distr_cache[k], prob, per_n_tk)

        # Character frequency distribution
        if tp == 'chr' or tp == 'char':
            self.fq_distr_cache[k] = self._freq_distr_chr(subcorp_idx, text_idx, chinese_only)
            return normalize(self.fq_distr_cache[k], prob, per_n_tk)
        
        # Character component frequency distribution
        fq_ch = self._freq_distr_chr(subcorp_idx, text_idx, chinese_only)
        if tp == "idc" or tp == "rad":
            if use_chr_types:
                fq_ch = Counter(fq_ch.keys())
            fq_compo = Counter()
            for ch, fq in fq_ch.items():
                ky = "noChrData"
                if ch in self.cc_map:
                    ky = self.cc_map[ch].get(tp, "noCompoData")
                fq_compo.update({ky: fq})
            return normalize(fq_compo, prob, per_n_tk)
        
        # Token distribution within a radical/component
        if radical:
            chars = self.rad_map.get(radical, set())
            chars.intersection_update(fq_ch.keys())
            return normalize(
                Counter({ch:fq for ch, fq in fq_ch.items() if ch in chars}), 
                prob, per_n_tk
            )
        if compo:
            chars = self._component_search(compo, idc, pos)
            chars.intersection_update(fq_ch.keys())
            return normalize(
                Counter({ch:fq for ch, fq in fq_ch.items() if ch in chars}),
                prob, per_n_tk
            )


    def _freq_distr_chr(self, subcorp_idx:int=None, text_idx:int=None, chinese_only=True):
        if isinstance(text_idx, int) and isinstance(subcorp_idx, int):
            for i, sc in enumerate(self.corpus):
                if subcorp_idx == i: 
                    for j, text in enumerate(sc['text']):
                        if j == text_idx:
                            return prun(
                                Counter(chain.from_iterable(text['c'])),
                                chinese_only
                            )
        elif isinstance(subcorp_idx, int):
            for i, sc in enumerate(self.corpus):
                if i == subcorp_idx:
                    corp = (c for t in sc['text'] for c in t['c'])
                    return prun(
                        Counter(chain.from_iterable(corp)),
                        chinese_only
                    )
        else:
            corp = (c for sc in self.corpus for t in sc['text'] for c in t['c'])
            return prun(Counter(chain.from_iterable(corp)), chinese_only)


    def _build_cc_map(self):
        for ch in self.chars:
            idc = ctree.ids_map.get(ch, [None])[0]
            rad = radicals.query(ch)[0]
            dph = None
            if idc is not None:
                idc = idc.idc
                dph = ctree.query(ch, use_flag="shortest", max_depth=-1)[0]
                if not isinstance(dph, str):
                    dph = dph.depth()
                else:
                    dph = 0
            if idc is None and rad == '': continue
            self.cc_map[ch] = {
                'idc': idc,
                'rad': rad,
                'dph': dph
            }
    
    def _build_rad_map(self):
        for ch in self.cc_map:
            r = self.cc_map[ch]['rad']
            self.rad_map.setdefault(r, set()).add(ch)

    def _build_idc_map(self):
        idc_val_nm = { x.value: x.name for x in IDC }
        for ch in self.chars:
            idc = ctree.ids_map.get(ch, [None])[0]
            if idc is None: 
                idc = "NULL"
            else:
                idc = idc.idc
            idc_nm = idc_val_nm.get(idc, "NULL")
            self.idc_map.setdefault(idc_nm, set()).add(ch)


def prun(x: Counter, chinese=True):
    if chinese:
        return Counter({
            k:x[k] for k in x if PAT_CH_CHR.match(k)
        })
    return x


def normalize(x: Counter, prob=True, per_n_tk=1):
    if not prob: return x
    N = sum(x.values())
    return { k: per_n_tk * v / N for k, v in x.items() }
