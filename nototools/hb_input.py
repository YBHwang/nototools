# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from fontTools.ttLib import TTFont

from nototools import summary


class HbInputGenerator(object):
    """Provides functions to generate harbuzz input.

    The input is returned as a list of strings, suitable for passing into
    subprocess.call or something similar.
    """

    def __init__(self, font):
        self.font = font
        self.reverse_cmap = build_reverse_cmap(self.font)

    def all_inputs(self, warn=False):
        """Generate harfbuzz inputs for all glyphs in a given font."""

        inputs = []
        glyph_names = self.font.getGlyphOrder()
        glyph_set = self.font.getGlyphSet()
        for name in glyph_names:
            is_zero_width = glyph_set[name].width == 0
            cur_input = self.input_from_name(name, pad=is_zero_width)
            if cur_input is not None:
                inputs.append(cur_input)
            elif warn:
                print('not tested (unreachable?): %s' % name)
        return inputs

    def input_from_name(self, name, features=(), pad=False):
        """Given glyph name, return input to harbuzz to render this glyph in the
        form of a (features, text) tuple, where `features` is a list of feature
        tags to activate and `text` is an input string.
        """

        # see if this glyph has a simple unicode mapping
        if name in self.reverse_cmap:
            text = unichr(self.reverse_cmap[name])
            if pad:
                text = '  ' + text
            return features, text

        # nope, check the substitution features
        if 'GSUB' not in self.font:
            return
        gsub = self.font['GSUB'].table
        if gsub.LookupList is None:
            return
        for lookup_index, lookup in enumerate(gsub.LookupList.Lookup):
            for st in lookup.SubTable:

                # see if this glyph can be a single-glyph substitution
                if lookup.LookupType == 1:
                    for glyph, subst in st.mapping.items():
                        if subst == name:
                            return self._input_with_context(
                                gsub, glyph, lookup_index, features)

                # see if this glyph is a ligature
                elif lookup.LookupType == 4:
                    for prefix, ligatures in st.ligatures.items():
                        for ligature in ligatures:
                            if ligature.LigGlyph == name:
                                glyphs = [prefix] + ligature.Component
                                return self._sequence_from_glyph_names(
                                    glyphs, features)


    def _input_with_context(self, gsub, glyph, lookup_index, features):
        """Given GSUB, input glyph, and lookup index, return input to harfbuzz
        to render the input glyph with the referred-to lookup activated.
        """

        # try to get a feature tag to activate this lookup
        for feature in gsub.FeatureList.FeatureRecord:
            if lookup_index in feature.Feature.LookupListIndex:
                features += (feature.FeatureTag,)
                return self.input_from_name(glyph, features)

        # try for a chaining substitution
        for lookup in gsub.LookupList.Lookup:
            for st in lookup.SubTable:
                if lookup.LookupType != 6:
                    continue
                for sub_lookup in st.SubstLookupRecord:
                    if sub_lookup.LookupListIndex != lookup_index:
                        continue
                    if st.LookAheadCoverage:
                        glyphs = [glyph, st.LookAheadCoverage[0].glyphs[0]]
                    elif st.BacktrackCoverage:
                        glyphs = [st.BacktrackCoverage[0].glyphs[0], glyph]
                    else:
                        continue
                    return self._sequence_from_glyph_names(glyphs, features)

        raise ValueError('Lookup list index %d not found.' % lookup_index)


    def _sequence_from_glyph_names(self, glyphs, features):
        """Return a sequence of glyphs from glyph names."""

        text = []
        for glyph in glyphs:
            features, cur_text = self.input_from_name(glyph, features)
            text.append(cur_text)
        return features, ''.join(text)


def build_reverse_cmap(font):
    """Build a dictionary mapping glyph names to unicode values."""

    return {n: v for v, n in summary.get_largest_cmap(font).items()}
