"""
    Copyright 2021 Inmanta

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
import os
import re
import subprocess
from typing import List

import inmanta
from inmanta import config
from inmanta.ast.attribute import RelationAttribute
from inmanta.ast.entity import Entity
from inmanta.data import convert_boolean
from inmanta.export import export


class ParseException(Exception):
    pass


OPT_RE = re.compile(r"""\s?(:?([^,=]+)=("[^"]+"|[^,]+))+""")


class Config(object):
    """
    Diagram configuration
    """

    def __init__(self, collector, line):
        self.collector = collector
        self.parse_line(line)

    def parse_line(self, line):
        raise NotImplementedError()

    def _parse_options(self, options_string):
        opt_list = OPT_RE.findall(options_string)
        return {key: value for _, key, value in opt_list}


class EntityConfig(Config):
    """
    Entity instance configuration
    """

    re = re.compile(r"^(?P<entity>[^:]+::[^.\[]+)(\[(?P<options>([^,\]]+,?)*)\])?$")

    def __init__(self, collector, line):
        self.entity = None
        self.options = {}
        self.container = False
        Config.__init__(self, collector, line)

    def parse_line(self, line):
        match = EntityConfig.re.search(line)
        if not match:
            raise ParseException()

        matches = match.groupdict()
        self.entity = matches["entity"]

        if "options" in matches and matches["options"]:
            self.options = self._parse_options(matches["options"])

        self.container = convert_boolean(self.options.get("container", False))
        self.label = self.options.get("label", None)
        if "label" in self.options:
            del self.options["label"]

    def collect(self, scope):
        if self.entity not in scope:
            return

        instances = scope[self.entity].get_all_instances()

        for instance in instances:
            options = dict(self.options)
            attributes = {k: v.value for k, v in instance.slots.items()}

            if self.label is not None:
                if self.label in attributes:
                    options["label"] = attributes[self.label]
                elif self.label[0] == '"' and self.label[-1] == '"':
                    options["label"] = self.label[1:-1].format_map(attributes)

            elif "name" in attributes:
                options["label"] = attributes["name"]

            else:
                options["label"] = repr(instance)

            self.collector.add_node(Node(instance, subgraph=self.container, **options))

    def __repr__(self):
        return self.entity + " -> " + ", ".join(["%s=%s" % x for x in self.options.items()])


class RelationConfig(Config):
    """
    Instance relation configuration
    """

    re = re.compile(r"^(?P<entity>[^:]+::[^.]+)(?P<relations>(\.[^\[]+)+)(\[(?P<options>([^,\]]+,?)*)\])?")

    def __init__(self, collector, line):
        self.entity = None
        self.options = {}
        self.relation = []
        self.type = None
        Config.__init__(self, collector, line)

    def parse_line(self, line):
        match = RelationConfig.re.search(line)

        if not match:
            raise ParseException()

        matches = match.groupdict()
        self.entity = matches["entity"]

        if "options" in matches and matches["options"]:
            self.options = self._parse_options(matches["options"])

        self.relation = [x for x in matches["relations"].split(".") if x]
        self.type = self.options.get("type", None)

    def collect_targets(self, instance, paths):
        """
        Collect the list of targets given the instance and the path list
        """
        if instance is None:
            return []
        attributes = {k: v.value for k, v in instance.slots.items()}
        targets = []
        if not paths:
            return [instance]

        path = paths[0]
        if path not in attributes:
            return targets

        values = attributes[path]
        if isinstance(values, list):
            for value in values:
                targets.extend(self.collect_targets(value, paths[1:]))
        else:
            targets.extend(self.collect_targets(values, paths[1:]))

        return targets

    def collect(self, scope):
        if self.entity not in scope:
            return

        instances = scope[self.entity].get_all_instances()

        for instance in instances:
            targets = self.collect_targets(instance, self.relation)

            for target in targets:
                if self.type == "contained_in":
                    target_node = self.collector.get_or_add(target)
                    from_node = self.collector.get_or_add(instance)
                    target_node.add_child(from_node)
                elif self.type == "contained_by":
                    target_node = self.collector.get_or_add(target)
                    from_node = self.collector.get_or_add(instance)
                    from_node.add_child(target_node)
                else:
                    self.collector.add_relation(instance, target, **self.options)

    def __repr__(self):
        return self.entity + " -> " + repr(self.relation) + " -> " + ", ".join(["%s=%s" % x for x in self.options.items()])


PARSERS = [EntityConfig, RelationConfig]


def parse_config_line(collector, line):
    for parser in PARSERS:
        try:
            return parser(collector, line)
        except ParseException:
            pass


class Node(object):
    """
    A graphviz node
    """

    def __init__(self, node_id, subgraph=False, **props):
        self.node_id = node_id
        self.props = props
        self.subgraph = subgraph
        self.children = []

    def add_child(self, child):
        """
        Add a child. This will automatically convert this node to a subgraph
        """
        self.subgraph = True
        self.children.append(child)

    def to_dot(self) -> "List[str]":
        if not self.subgraph:
            options = ",".join(['%s="%s"' % x for x in self.props.items()])
            return ['"%s" [%s];' % (self, options)]
        else:
            node_strings = ["subgraph cluster_{0} {{".format(self)]
            node_strings += ['  {key}="{value}"'.format(key=k, value=v) for k, v in self.props.items()]
            node_strings += ['  "{0}";'.format(str(child)) for child in self.children]
            node_strings += ["}"]

            return node_strings

    def get_id(self):
        if not self.subgraph:
            return str(self)
        else:
            return f"cluster_{ str(self)}"

    def __str__(self):
        return str(id(self.node_id))

    def merge_node(self, other):
        """
        Merge the settings of the given node
        """
        self.props.update(other.props)
        self.subgraph = other.subgraph
        self.children.extend(other.children)


class Relation(object):
    """
    A graphviz edge between two nodes
    """

    def __init__(self, relation_id, from_node, to_node, **props):
        self.relation_id = relation_id
        self.from_node = from_node
        self.to_node = to_node
        self.props = props

    def to_dot(self):
        from_id = self.from_node.get_id()
        to_id = self.to_node.get_id()

        if self.from_node.subgraph and self.from_node.children:
            self.props["ltail"] = from_id
            # select random one of the children, otherwise graphviz complains
            from_id = str(self.from_node.children[0])

        if self.to_node.subgraph and self.to_node.children:
            self.props["lhead"] = to_id
            # select random one of the children, otherwise graphviz complains
            to_id = str(self.to_node.children[0])

        options = ",".join(['%s="%s"' % x for x in self.props.items() if x[1] is not None])
        if not options:
            return '"%s" -- "%s";\n' % (from_id, to_id)
        else:
            return '"%s" -- "%s" [%s];\n' % (from_id, to_id, options)


class GraphCollector(object):
    def __init__(self):
        self.relations = dict()
        self.parents = dict()
        self.nodes = {}

    def add_node(self, node: Node) -> None:
        if node.node_id not in self.nodes:
            self.nodes[node.node_id] = node
        else:
            self.nodes[node.node_id].merge_node(node)
        return node

    def get_node(self, instance: "inmanta.execute.runtime.Instance") -> "Node":
        """
        Get the node that represents the given instance
        """
        if instance in self.nodes:
            return self.nodes[instance]
        return None

    def get_or_add(self, instance: "inmanta.execute.runtime.Instance") -> "Node":
        """
        Get or add a node
        """
        node = self.get_node(instance)
        if node is None:
            node = self.add_node(Node(instance))

        return node

    def add_relation(self, from_instance, to_instance, label=None, **kwargs):
        """
        Add relation, overwrite any duplicate with same label and same ends (even if ends are swapped)
        """
        from_node = self.get_or_add(from_instance)
        to_node = self.get_or_add(to_instance)

        node_list = sorted([str(from_node), str(to_node)])
        idx = (node_list[0], node_list[1], label)

        self.relations[idx] = Relation(idx, from_node, to_node, label=label, **kwargs)

    # def add_parent(self, fro, to):
    #     self.parents[(id(fro), id(to))] = (id(fro), id(to))
    #     self.add_node(Node(id=id(to), label=to))

    # def add_keyed(self, key, fro, to, label=None):
    #     """
    #         Add relation, overwrite any duplicate with same key best used for items with a natural ordering,
    #         such as parent child, where the key is (child, parent)
    #     """
    #     self.relations[key] = Relation(id, fro, to, label=label)
    #     self.add_node(Node(id=id(fro), label=fro))
    #     self.add_node(Node(id=id(to), label=to))

    # def add_dual_keyed(self, key, key2, fro, to, label=None):
    #     """
    #         Add relation, overwrite any duplicate with same key ends (even if they are swapped) best used for pairs of
    #         relations
    #     """
    #     l = sorted([id(key), id(key2)])

    #     idx = ("dx", l[0], l[1])

    #     self.relations[idx] = Relation(id, fro, to, label=label)

    #     self.add_node(Node(id=id(fro), label=fro))
    #     self.add_node(Node(id=id(to), label=to))

    def dump_dot(self):
        dot = "  compound=true;\n"

        dot += "\n".join(["  " + line for node in self.nodes.values() for line in node.to_dot()])
        dot += "\n"

        for rel in self.relations.values():
            dot += "  " + rel.to_dot()

        for rel in self.parents:
            dot += '"%s" -- "%s" [dir=forward];\n' % (rel[0], rel[1])

        return dot

    # def dump_plant_uml(self):
    #     dot = ""

    #     for node in self.nodes:
    #         dot += 'class %s{\n' % (node.get_full_name().replace(":", "_"))
    #         for attrib in node.attributes.values():
    #             if not isinstance(attrib, RelationAttribute):
    #                 dot += ' %s %s \n' % (str(attrib.get_type()).replace('<', '').replace('>', '').replace(' ', '_'),
    #                                       attrib.get_name())
    #         dot += '}\n'

    #     for rel in self.parents:
    #         dot += '%s --> %s\n' % (rel[0].get_full_name().replace(":", "_"), rel[1].get_full_name().replace(":", "_"))

    #     for rel in self.relations.values():
    #         if len(rel) == 5:
    #             dot += '%s "%s" -- "%s" %s \n' % (rel[0].get_full_name().replace(":", "_"),
    #                                               rel[3], rel[4], rel[1].get_full_name().replace(":", "_"))
    #         else:
    #             dot += '%s -- %s \n' % (rel[0].get_full_name().replace(":", "_"), rel[1].get_full_name().replace(":", "_"))

    #     return dot


def parse_cfg(cfg):
    entries = cfg.replace("]", "").split(",")
    result = {}
    for entry in entries:
        opt, value = entry.split("=")
        result[opt] = value

    return result


def is_type(instance, type):
    return instance.type == type or instance.type.is_subclass(type)


def parse_entity(line, scope, relcollector):
    parts = line.split("::")
    rel = False
    parents = False

    if parts[-1] == "*":
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    elif parts[-1] == "**":
        parts[-1] = "*"
        rel = True
        parents = True
        line = "::".join(parts)
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    elif parts[-1] == "*+":
        parts[-1] = "*"
        parents = True
        line = "::".join(parts)
        types = [t for (k, t) in scope.items() if re.search(line, k)]
    else:
        types = scope[line]

    dot = ""
    for type_def in types:
        relcollector.add_node(Node(id(type_def), label=type_def.get_full_name()))
        if rel:
            add_relations(type_def, relcollector)
        if parents:
            add_parents(type_def, relcollector)

    return dot


def add_relations(entity, relcollector):
    for att in entity.get_attributes().values():
        if isinstance(att, RelationAttribute):
            relcollector.add_dual_keyed(att.end, att.end.end, entity, att.end.entity, att.get_name())


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
                label = cfg["label"].strip('"')
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


def generate_dot(name, diagram_config, types):
    dot = "graph {\n"
    dot += "  // name: {0}\n".format(name)

    relations = GraphCollector()
    collect_graph(diagram_config, types, relations)
    dot += relations.dump_dot()

    return dot + "}\n"


def generate_plant_uml(config, scope):
    dot = "@startuml\n"
    relations = GraphCollector()

    collect_graph(config, scope, relations)

    dot += relations.dump_plant_uml()

    return dot + "@enduml\n"


def collect_graph(diagram_config, scope, collector):
    for line in diagram_config.split("\n"):
        config_line = parse_config_line(collector, line)
        if config_line is not None:
            config_line.collect(scope)

    # for t in types:
    #     if t[0] == "@":
    #         parse_entity(t[1:], scope, relations)
    #     else:
    #         parse_instance(t, scope, relations)

    # for link in links:
    #     if link[0] == "@":
    #         parse_class_relation(link[1:], scope, relations)
    #     else:
    #         parse_instance_relation(link, scope, relations)


def generate_plantuml(
    moduleexpression,
    types,
    parents_to_root=True,
    relations_escape=True,
    attributes=True,
):
    moduleexpression = [re.compile(r) for r in moduleexpression]

    def name_matches(name):
        return any((r.match(name) for r in moduleexpression))

    # collect types
    mytypes = {k: v for k, v in types.items() if name_matches(k) and isinstance(v, Entity)}

    # collect relations
    allrelations = [r for e in mytypes.values() for r in e.get_attributes().values() if isinstance(r, RelationAttribute)]
    if not relations_escape:
        allrelations = [r for r in allrelations if r.get_type().get_full_name() in mytypes]

    # We use a dict to benefit from insertion-order in order to have deterministic plantuml
    # see https://github.com/inmanta/graph/pull/100
    paired = dict()
    for r in allrelations:
        if r.end not in paired:
            paired[r] = None

    def emit_class(entity):
        if not attributes:
            return "class %s" % entity.get_full_name()
        else:
            myattributes = [r for r in entity.get_attributes().values() if not isinstance(r, RelationAttribute)]
            atts = ["%s %s" % (a.get_type().type_string(), a.get_name()) for a in myattributes]
            return """class %s {
    %s
}""" % (
                entity.get_full_name(),
                "\n".join(atts),
            )

    # emit classes
    classes = [emit_class(cl) for cl in mytypes.values()]
    # emit inheritance
    inh = [
        "%(parent)s <|-- %(child)s" % {"parent": parent, "child": child}
        for child in mytypes.values()
        for parent in child.parent_entities
        if parent.get_full_name() != "std::Entity" and (parents_to_root or parent.get_full_name() in mytypes)
    ]

    # emit relations
    def arity(r):
        if r.low == 1:
            if r.high == 1:
                return "1"
            if r.high is None:
                return "+"
        if r.low == 0:
            if r.high == 1:
                return "?"
            if r.high is None:
                return "*"
        return "[%d:%s]" % (r.low, r.high if r.high is not None else "")

    def emit_relation(r):
        if r.end is None:
            return '%s "%s" -->  %s: %s' % (
                r.get_entity().get_full_name(),
                arity(r),
                r.get_type().get_full_name(),
                r.get_name(),
            )
        else:
            return """%s "%s" -- "%s" %s : %s >""" % (
                r.get_entity().get_full_name(),
                arity(r),
                arity(r.end),
                r.get_type().get_full_name(),
                r.get_name(),
            )

    rel = [emit_relation(r) for r in paired.keys()]

    return "\n".join(classes + inh + rel)


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
        dot = generate_dot(graph.name, graph.config, exporter.types)
        filename = os.path.join(outdir, "%s.dot" % graph.name)

        with open(filename, "w+") as fd:
            fd.write(dot)

        for file_type in file_types:
            try:
                subprocess.check_call(
                    [
                        "dot",
                        "-T%s" % file_type,
                        "-Goverlap=scale",
                        "-Gdefaultdist=0.1",
                        "-Gsplines=true",
                        "-Gsep=.1",
                        "-Gepsilon=.0000001",
                        "-o",
                        os.path.join(outdir, "%s.%s" % (graph.name, file_type)),
                        filename,
                    ]
                )
            except Exception:
                print(
                    "Could not render graph, please execute "
                    + " ".join(
                        [
                            "dot",
                            "-T%s" % file_type,
                            "-Goverlap=scale",
                            "-Gdefaultdist=0.1",
                            "-Gsplines=true",
                            "-Gsep=.1",
                            "-Gepsilon=.0000001",
                            "-o",
                            os.path.join(outdir, "%s.%s" % (graph.name, file_type)),
                            filename,
                        ]
                    )
                )


@export("classdiagram", "graph::ClassDiagram")
def export_classdiagram(exporter, types):
    outdir = config.Config.get("graph", "output-dir", ".")
    if outdir is None:
        return

    if not os.path.exists(outdir):
        os.mkdir(outdir)

    # Get all diagrams
    diagram_type = types["graph::ClassDiagram"]
    for graph in diagram_type:
        cdiag = generate_plantuml(graph.moduleexpression, exporter.types)
        filename = os.path.join(outdir, "%s.puml" % graph.name)

        with open(filename, "w+") as fd:
            fd.write("@startuml\n")
            if graph.header != "":
                fd.write(graph.header + "\n")
            fd.write(cdiag)
            fd.write("\n@enduml\n")


# @export("classdiagram", "graph::Graph")
# def export_plantuml(exporter, types):
#     outdir = config.Config.get("graph", "output-dir", ".")
#     if outdir is None:
#         return

#     if not os.path.exists(outdir):
#         os.mkdir(outdir)

#     file_types = [x.strip() for x in config.Config.get("graph", "types", "png").split(",")]

#     # Get all diagrams
#     diagram_type = types["graph::Graph"]

#     for graph in diagram_type:
#         dot = generate_plant_uml(graph.config, exporter._scope)
#         filename = os.path.join(outdir, "%s.puml" % graph.name)

#         with open(filename, "w+") as fd:
#             fd.write(dot)

# #        for t in file_types:
# #            retcode = subprocess.call(["dot", "-T%s" % t, "-Goverlap=scale",
# #                "-Gdefaultdist=0.1", "-Gsplines=true", "-Gsep=.1",
# #                "-Gepsilon=.0000001", "-o", os.path.join(outdir, "%s.%s" % (graph.name, t)), filename])
