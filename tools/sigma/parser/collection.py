# Sigma parser
# Copyright 2016-2018 Thomas Patzke, Florian Roth

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import yaml
from .exceptions import SigmaCollectionParseError
from .rule import SigmaParser

class SigmaCollectionParser:
    """
    Parses a Sigma file that may contain multiple Sigma rules as different YAML documents.

    Special processing of YAML document if 'action' attribute is set to:

    * global: merges attributes from document in all following documents. Accumulates attributes from previous set_global documents
    * reset: resets global attributes from previous set_global statements
    * repeat: takes attributes from this YAML document, merges into previous rule YAML and regenerates the rule
    """
    def __init__(self, content, config=None, rulefilter=None, filename=None):
        if config is None:
            from sigma.configuration import SigmaConfiguration
            config = SigmaConfiguration()
        self.yamls = yaml.safe_load_all(content)
        globalyaml = dict()
        self.parsers = list()
        prevrule = None
        if filename:
            try:
                globalyaml['yml_filename']=str(filename.name)
                globalyaml['yml_path']=str(filename.parent)
            except:
                filename = None
        
        for yamldoc in self.yamls:
            action = None
            try:
                action = yamldoc['action']
                del yamldoc['action']
            except KeyError:
                pass

            if action == "global":
                deep_update_dict(globalyaml, yamldoc)
            elif action == "reset":
                globalyaml = dict()
                if filename:
                    globalyaml['yml_filename']=str(filename.name)
                    globalyaml['yml_path']=str(filename.parent) 
            elif action == "repeat":
                if prevrule is None:
                    raise SigmaCollectionParseError("action 'repeat' is only applicable after first valid Sigma rule")
                newrule = prevrule.copy()
                deep_update_dict(newrule, yamldoc)
                if rulefilter is None or rulefilter is not None and not rulefilter.match(newrule):
                    self.parsers.append(SigmaParser(newrule, config))
                    prevrule = newrule
            else:
                deep_update_dict(yamldoc, globalyaml)
                if rulefilter is None or rulefilter is not None and rulefilter.match(yamldoc):
                    self.parsers.append(SigmaParser(yamldoc, config))
                    prevrule = yamldoc
        self.config = config

    def generate(self, backend):
        """Calls backend for all parsed rules"""
        backend_name = backend.identifier
        rules = list()
        for parser in self.parsers:
            yaml = parser.parsedyaml
            search_prefix = yaml.get("search_prefix", {}).get(backend_name, "")
            search_postfix = yaml.get("search_postfix", {}).get(backend_name, "")
            baserule = backend.generate(parser)
            # Ensure prefix and postfix don't interfere with filtering Nones and Empty Strings
            rule = search_prefix + baserule + search_postfix if baserule else baserule
            rules.append(rule)
        return filter(lambda x: bool(x), rules) # filter None's and empty strings

    def __iter__(self):
        return iter([parser.parsedyaml for parser in self.parsers])

def deep_update_dict(dest, src):
    for key, value in src.items():
        if isinstance(value, dict) and key in dest and isinstance(dest[key], dict):     # source is dict, destination key already exists and is dict: merge
                deep_update_dict(dest[key], value)
        else:
            dest[key] = value
