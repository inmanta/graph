"""
    Inmanta graphing module

    :copyright: 2018 Inmanta
    :contact: code@inmanta.com
    :license: Inmanta EULA
"""
import os
import subprocess
import re

from inmanta import config
from inmanta.export import export
from inmanta.ast.attribute import RelationAttribute
from inmanta.execute.proxy import DynamicProxy


class Config(object):
    """
        Diagram configuration
    """


class EntityConfig(Config):
    """
        Entity instance configuration
    """
    def __init__(self, line):
        pass


class RelationConfig(Config):
    pass


class Node(object):
    def __init__(self, id, **props):
        self.id = id
        self.props = props

    def to_dot(self):
        options = ",".join(['%s="%s"' % x for x in self.props.items()])
        return '"%s" [%s];\n' % (self.id, options)


class Relation(object):
    def __init__(self, id, fro, to, **props):
        self.id = id
        self.fro = fro
        self.to = to
        self.props = props

    def to_dot(self):
        if len(self.props) == 0:
            return '"%s" -- "%s";\n' % (id(self.fro), id(self.to))
        else:
            options = ",".join(['%s="%s"' % x for x in self.props.items()])
            return '"%s" -- "%s" [%s];\n' % (id(self.fro), id(self.to), options)


# FIXME: do not put tuples of different length into one dict
class GraphCollector(object):

    def __init__(self):
        self.relations = dict()
        self.parents = dict()
        self.nodes = {}

    def addNode(self, node):
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add(self, fro, to, label=None):
        """
            Add relation, overwrite any duplicate with same label and same ends (even if ends are swapped)
        """
        l = sorted([id(fro), id(to)])
        self.addNode(Node(id=id(fro), label=fro))
        self.addNode(Node(id=id(to), label=to))
        idx = ("a", l[0], l[1], label)
        self.relations[idx] = Relation(idx, fro, to, label=label)

    def add_parent(self, fro, to):
        self.parents[(id(fro), id(to))] = (id(fro), id(to))
        self.addNode(Node(id=id(to), label=to))


    def addKeyed(self, key, fro, to, label=None):
        """add relation, overwrite any duplicate with same key
            best used for items with a natural ordering, such as parent child, where the key is (child,parent)"""
        self.relations[key] = Relation(id, fro, to, label=label)
        self.addNode(Node(id=id(fro), label=fro))
        self.addNode(Node(id=id(to), label=to))

    def addDualKeyed(self, key, key2, fro, to, label=None):
        """add relation, overwrite any duplicate with same key ends (even if they are swapped)
            best used for pairs of relations"""
        l = sorted([id(key), id(key2)])

        idx = ("dx", l[0], l[1])

        self.relations[idx] = Relation(id, fro, to, label=label)

        self.addNode(Node(id=id(fro), label=fro))
        self.addNode(Node(id=id(to), label=to))

    def dump_dot(self):
        dot = ""

        for node in self.nodes.values():
            dot += node.to_dot()

        for rel in self.relations.values():
            dot += rel.to_dot()

        for rel in self.parents:
            dot += '"%s" -- "%s" [dir=forward];\n' % (rel[0], rel[1])

        return dot

    def dumpPlantUML(self):
        dot = ""

        for node in self.nodes:
            dot += 'class %s{\n' % (node.get_full_name().replace(":", "_"))
            for attrib in node.attributes.values():
                if not isinstance(attrib, RelationAttribute):
                    dot += ' %s %s \n' % (str(attrib.get_type()).replace('<', '').replace('>', '').replace(' ', '_'),
                                          attrib.get_name())
            dot += '}\n'

        for rel in self.parents:
            dot += '%s --> %s\n' % (rel[0].get_full_name().replace(":", "_"), rel[1].get_full_name().replace(":", "_"))

        for rel in self.relations.values():
            if len(rel) == 5:
                dot += '%s "%s" -- "%s" %s \n' % (rel[0].get_full_name().replace(":", "_"),
                                                  rel[3], rel[4], rel[1].get_full_name().replace(":", "_"))
            else:
                dot += '%s -- %s \n' % (rel[0].get_full_name().replace(":", "_"), rel[1].get_full_name().replace(":", "_"))

        return dot


def parse_cfg(cfg):
    entries = cfg.replace("]", "").split(",")
    result = {}
    for entry in entries:
        opt, value = entry.split("=")
        result[opt] = value

    return result


def is_type(instance, type):
    return instance.type == type or instance.type.is_subclass(type)


# FIXME: does not use relation collector, as such only dot output can use it,...
def parse_instance(line, scope, collector):
    cfg = line.split("[")
    type_name = cfg[0]
    if type_name not in scope:
        return ""

    instances = scope[type_name].get_all_instances()

    if len(cfg) == 2:
        cfg = parse_cfg(cfg[1])
    else:
        cfg = {"label": "name"}

    dot = ""
    for instance in instances:
        attributes = {k: v.value for k, v in instance.slots.items()}
        options = cfg.copy()
        if "label" in cfg:
            opt = cfg["label"]

            if opt in attributes:
                options['label'] = attributes[opt]
            elif opt[0] == '"' and opt[-1] == '"':
                options['label'] = opt[1:-1].format_map(attributes)
        else:
            options['label'] = repr(instance)

        collector.addNode(Node(id(instance), **options))

    return dot


def parse_entity(line, scope, relcollector):
    parts = line.split("::")
    rel = False
    parents = False

    if parts[-1] == '*':
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    elif parts[-1] == '**':
        parts[-1] = '*'
        rel = True
        parents = True
        line = "::".join(parts)
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    elif parts[-1] == '*+':
        parts[-1] = '*'
        parents = True
        line = "::".join(parts)
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    else:
        types = scope[line]

    dot = ""
    for type_def in types:

        relcollector.addNode(Node(id(type_def), label=type_def.get_full_name()))
        if rel:
            add_relations(type_def, relcollector)
        if parents:
            add_parents(type_def, relcollector)

    return dot


def add_relations(entity, relcollector):
    for att in entity.get_attributes().values():
        if isinstance(att, RelationAttribute):
            relcollector.addDualKeyed(att.end, att.end.end, entity, att.end.entity, att.get_name())


def add_parents(entity, relcollector):
    for parent in entity.parent_entities:
        if parent.get_full_name() != "std::Entity":
            relcollector.add_parent(entity, parent)


def relation_options(line):
    cfg = line.split("[")
    relation_name = cfg[0]

    if len(cfg) == 2:
        cfg = parse_cfg(cfg[1])

    return relation_name, cfg


def parse_instance_relation(link, types, relcollector):
    parts = link.split(".")
    t = parts[0]
    links = parts[1:]

    # get the objects
    instances = types[t].get_all_instances()

    for instance in instances:
        targets = [("", instance, "")]
        for link in links:
            link, cfg = relation_options(link)

            tfilter = None
            if "|" in link:
                p = link.split("|")
                if len(p) != 2:
                    raise Exception("Invalid use of | in %s" % link)

                link = p[0]
                tfilter = p[1]
                tfilter = types[tfilter]

            new = []
            for name, x, _ in targets:
                result = x.get_attribute(link).value
                if isinstance(result, list):
                    new.extend(result)
                else:
                    new.append(result)

            if "label" in cfg:
                label = cfg["label"].strip("\"")
            else:
                label = link

            if tfilter is not None:
                targets.extend([(link, x, label) for x in new if is_type(x, tfilter)])
            else:
                targets.extend([(link, x, label) for x in new])

        for link, target, label in targets:
            if instance is not target:
                relcollector.add(instance, target, label=label)


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
            relcollector.add_parent(type_def, parent)

    elif type_def.has_attribute(links):
        rel = type_def.get_attribute(links)
        relcollector.add(type_def, rel.type)


def generate_dot(config, types):
    dot = "graph {\n"
    relations = GraphCollector()

    collect_graph(config, types, relations)

    dot += relations.dump_dot()

    return dot + "}\n"


def generate_plantUML(config, scope):
    dot = "@startuml\n"
    relations = GraphCollector()

    collect_graph(config, scope, relations)

    dot += relations.dumpPlantUML()

    return dot + "@enduml\n"


def collect_graph(config, scope, relations):
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
            parse_entity(t[1:], scope, relations)
        else:
            parse_instance(t, scope, relations)

    for link in links:
        if link[0] == "@":
            parse_class_relation(link[1:], scope, relations)
        else:
            parse_instance_relation(link, scope, relations)


@export("graph", "graph::Graph")
def export_graph(exporter, types):
    outdir = config.Config.get("graph", "output-dir", ".")
    if outdir is None:
        return

    if not os.path.exists(outdir):
        os.mkdir(outdir)

    file_types = [x.strip() for x in config.Config.get("graph", "types", "png").split(",")]

    # Get all diagrams
    diagram_type = types["graph::Graph"]

    for graph in diagram_type:
        dot = generate_dot(graph.config, exporter.types)
        filename = os.path.join(outdir, "%s.dot" % graph.name)

        with open(filename, "w+") as fd:
            fd.write(dot)

        for file_type in file_types:
            subprocess.check_call(["dot", "-T%s" % file_type, "-Goverlap=scale",
                                   "-Gdefaultdist=0.1", "-Gsplines=true", "-Gsep=.1",
                                   "-Gepsilon=.0000001", "-o", os.path.join(outdir, "%s.%s" % (graph.name, file_type)),
                                   filename])


@export("classdiagram", "graph::Graph")
def export_plantuml(exporter, types):
    #outdir = exporter.config.get("graph", "output-dir")
    outdir = "."

    if outdir is None:
        return

    if not os.path.exists(outdir):
        os.mkdir(outdir)

#    if exporter.config.has_option("graph", "types"):
#        file_types = [x.strip() for x in exporter.config.get("graph", "types").split(",")]
#    else:
#        file_types = []
    file_types = ["png"]

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
