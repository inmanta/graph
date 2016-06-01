"""
    Copyright 2016 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: code@inmanta.com
"""


from Imp.export import export
from Imp.ast.attribute import RelationAttribute
from Imp.ast.enum import Enum

import os, subprocess

#FIXME: hack to prevent core bugs from triggering https://github.com/bartv/imp/issues/2
def getAttributeName(attrib):
    if isinstance(attrib, Enum):
        return "Enum"
    return attrib.get_name()

#FIXME: hack to prevent core bugs from triggering https://github.com/bartv/imp/issues/2
def getAttribType(attrib):
    if isinstance(attrib.get_type(), Enum):
        return "Enum"
     
    return str(attrib.get_type()).replace('<','').replace('>','').replace(' ','_')


#FIXME: do not put tuples of different length into one dict
class graphCollector(object):
    def __init__(self):
        self.relations = dict()
        self.parents=dict()
        self.nodes = set()
        
    def addNode(self, node):
        self.nodes.add(node)
    
    def add(self, fro, to, label=None):
        """add relation, overwrite any duplicate with same label and same ends (even if ends are swapped)"""
        l = sorted([id(fro), id(to)])
        self.nodes.add(fro)
        self.nodes.add(to)
        self.relations[("a", l[0], l[1], label)] = (fro, to, label)
        
    def addParent(self,fro,to):
        self.parents[(fro,to)]=(fro,to)
    
    def addKeyed(self, key, fro, to, label=None):
        """add relation, overwrite any duplicate with same key
            best used for items with a natural ordering, such as parent child, where the key is (child,parent)"""
        self.relations[key] = (fro, to, label)
        self.nodes.add(fro)
        self.nodes.add(to)
    
    def addDualKeyed(self, key, key2, fro, to, name=None, label=None):
        """add relation, overwrite any duplicate with same key ends (even if they are swapped)
            best used for pairs of relations"""
        l = sorted([id(key), id(key2)])
        
        i=1
        if(l[0]==id(key)):
            i=0     
        
        old=None
        if( ("dx", l[0], l[1]) in self.relations):
            old = self.relations[("dx", l[0], l[1])][ i ];
        
        if(i==0):
            self.relations[("dx", l[0], l[1])] = (fro, to, label,old,name)
        else:
            self.relations[("dx", l[0], l[1])] = (fro, to, label,name,old)
               
        self.nodes.add(fro)
        self.nodes.add(to)
    
    def dumpDot(self):
        dot = ""
        
        for node in self.nodes:
            dot += '  "%s" [label="%s",shape=rect];\n' % (id(node), node.get_full_name())
        
        for rel in self.relations.values():
            if rel[2] == None:
                dot += '"%s" -- "%s";\n' % (id(rel[0]), id(rel[1]))
            else:
                dot += '"%s" -- "%s" [%s];\n' %(id(rel[0]), id(rel[1]), rel[2])
        
        for rel in self.parents:
            dot +=  '"%s" -- "%s" [dir=forward];\n' %(id(rel[0]), id(rel[1]))
          
        return dot
    
    def dumpPlantUML(self):
        dot = ""
        
        for node in self.nodes:
            dot += 'class %s{\n' % (node.get_full_name().replace(":","_"))
            for attrib in node.attributes.values():
                if not isinstance(attrib, RelationAttribute):
                    dot+=' %s %s \n' % (getAttribType(attrib),getAttributeName(attrib)) 
            dot += '}\n'
        
        for rel in self.parents:
            dot +=  '%s --> %s\n' %(rel[0].get_full_name().replace(":","_"), rel[1].get_full_name().replace(":","_"))
            
        for rel in self.relations.values():
            if len(rel) == 5:
                dot += '%s "%s" -- "%s" %s \n' % (rel[0].get_full_name().replace(":","_"),rel[3],rel[4], rel[1].get_full_name().replace(":","_"))
            else:
                dot += '%s -- %s \n' % (rel[0].get_full_name().replace(":","_"), rel[1].get_full_name().replace(":","_"))
          
        return dot
        
        
        

def parse_cfg(cfg):
    entries = cfg.replace("]", "").split(",")
    
    result = {}
    for entry in entries:
        parts = entry.split("=")
        
        result[parts[0]] = parts[1]
        
    return result
    
def is_type(instance, typestring):
    parts = typestring.split("::")
    ns = parts[:-1]
    t = parts[-1]
    
    if instance.__class__.__name__ != t:
        return False
        
    if len(ns) > 0:
        raise Exception("Not implemented")
        
    return True


# FIXME: does not use relation collector, as such only dot output can use it,...
def parse_instance(line, scope):
    cfg = line.split("[")
    parts = cfg[0].split("::")
    instances = scope.get_variable(parts[-1], parts[:-1]).value
        
    if len(cfg) == 2:
        cfg = parse_cfg(cfg[1])
    else:
        cfg = {"label" : "name"}

    rank = None
    if "rank" in cfg:
        rank = cfg["rank"]
        del cfg["rank"]

    dot = ""
    for instance in instances:
        options = cfg.copy()
        if "label" in cfg and hasattr(instance, cfg["label"]):
            options['label'] = getattr(instance, cfg["label"])
        else:
            options['label'] = repr(instance)

        options = ",".join(['%s="%s"' % x for x in options.items()])
            
        dot += '"%s" [%s];\n' % (instance, options)

    if rank is not None:
        dot += "{ rank=%s; %s};\n" % (rank, "; ".join(['"%s"' % x for x in instances]))
        
    return dot

def parse_class(line, scope, relcollector):
    parts = line.split("::")
        
    if parts[-1].startswith('*'):
        subscope = scope.get_scope(parts[:-1])
        typedefs = subscope.get_variables()
    else:
        typedefs = [scope.get_variable(parts[-1], parts[:-1])]
    
    dot = ""
    for type_def in typedefs:
        type_def = type_def.value
        if hasattr(type_def, "get_full_name"):
            relcollector.addNode(type_def)    
            if parts[-1] == '**':
                addRelations(type_def, relcollector)
        
    
    return dot

def addRelations(entity, relcollector):
    for att in entity.get_attributes().values():
        if isinstance(att, RelationAttribute):
            relcollector.addDualKeyed(att.end, att.end.end, entity, att.end.entity,att.get_name(),"label=" + att.get_name())
    for parent in entity.parent_entities:
        if parent.get_full_name() != "std::Entity":
            relcollector.addParent(entity, parent)
            
    

def parse_instance_relation(link, scope, relcollector):
    parts = link.split(".")
    t = parts[0]
    links = parts[1:]
        
    # get the objects
    parts = t.split("::")
    instances = scope.get_variable(parts[-1], parts[:-1]).value
        
    for instance in instances:
        targets = [instance]
        for link in links:
            tfilter = None
            if "|" in link:
                p = link.split("|")
                if len(p) != 2:
                    raise Exception("Invalid use of | in %s" % link)
                    
                link = p[0]
                tfilter = p[1]
                
            new = []
            for x in targets:
                result = getattr(x, link)
                if isinstance(result, list):
                    new.extend(result)
                else:
                    new.append(result)
                
            if tfilter is not None:
                targets = [x for x in new if is_type(x, tfilter)]
            else:
                targets = new
            
        for target in targets:
            if instance is not target:
                relcollector.add(instance, target)

def parse_class_relation(link, scope, relcollector):
    parts = link.split(".")
    t = parts[0]
    links = parts[1:]
    
    if len(links) != 1:
        raise Exception("In class diagrams only one step relations are supported")
    links = links[0]
        
    # get the objects
    parts = t.split("::")
    type_def = scope.get_variable(parts[-1], parts[:-1]).value

    if links == "_parents":
        for parent in type_def.parent_entities:
            relcollector.addParent(type_def, parent)
        
    elif type_def.has_attribute(links):
        rel = type_def.get_attribute(links)
        relcollector.add(type_def, rel.type)

def generate_dot(config, scope):
    dot = "graph {\n"
    relations = graphCollector()    
   
    dot += collectGraph(config, scope, relations)
        
    dot += relations.dumpDot()
            
    return dot + "}\n"

def generate_plantUML(config, scope):
    dot = "@startuml\n"
    relations = graphCollector()    
   
    collectGraph(config, scope, relations)
        
    dot += relations.dumpPlantUML()
            
    return dot + "@enduml\n"

def collectGraph(config, scope, relations):
    dot = ""
    types = []
    links = []
    for line in config.split("\n"):
        line = line.strip()
        if len(line) > 0 and line[0] == "#":
            continue
        elif "." in line:
            links.append(line)
            
        elif line != "" and line[0] != " ":
            types.append(line)
            
    for t in types:
        if t[0] == "@":
            dot += parse_class(t[1:], scope, relations)
        else:
            dot += parse_instance(t, scope)
        
    
    for link in links:
        if link[0] == "@":
            parse_class_relation(link[1:], scope, relations)
        else:
            parse_instance_relation(link, scope, relations)
    return dot
           

@export("graph", "graph::Graph")
def export_graph(exporter, types):
    outdir = exporter.config.get("graph", "output-dir")
    
    if outdir is None:
        return

    if not os.path.exists(outdir):
        os.mkdir(outdir)
        
    if exporter.config.has_option("graph", "types"):
        file_types = [x.strip() for x in exporter.config.get("graph", "types").split(",")]
    else:
        file_types = []
        
    # Get all diagrams
    diagram_type = types["graph::Graph"]
    
    for graph in diagram_type:
        dot = generate_dot(graph.config, exporter._scope)
        filename = os.path.join(outdir, "%s.dot" % graph.name)
        
        with open(filename, "w+") as fd:
            fd.write(dot)
        
        for t in file_types:
            retcode = subprocess.call(["dot", "-T%s" % t, "-Goverlap=scale",
                "-Gdefaultdist=0.1", "-Gsplines=true", "-Gsep=.1",
                "-Gepsilon=.0000001", "-o", os.path.join(outdir, "%s.%s" % (graph.name, t)), filename])
                

@export("classdiagram", "graph::Graph")
def export_plantuml(exporter, types):
    outdir = exporter.config.get("graph", "output-dir")
    
    if outdir is None:
        return

    if not os.path.exists(outdir):
        os.mkdir(outdir)
        
    if exporter.config.has_option("graph", "types"):
        file_types = [x.strip() for x in exporter.config.get("graph", "types").split(",")]
    else:
        file_types = []
        
    # Get all diagrams
    diagram_type = types["graph::Graph"]
    
    for graph in diagram_type:
        dot = generate_plantUML(graph.config, exporter._scope)
        filename = os.path.join(outdir, "%s.puml" % graph.name)
        
        with open(filename, "w+") as fd:
            fd.write(dot)
        
#        for t in file_types:
#            retcode = subprocess.call(["dot", "-T%s" % t, "-Goverlap=scale",
#                "-Gdefaultdist=0.1", "-Gsplines=true", "-Gsep=.1",
#                "-Gepsilon=.0000001", "-o", os.path.join(outdir, "%s.%s" % (graph.name, t)), filename])
                
                
