# Usage

The graph module provides two exporters:
1. class diagram exporter to convert inmanta model into a [plantuml](https://plantuml.com/) class diagram
2. an instance diagram exporter that generates dot and png files based on a diagram definition.

This module is in Beta. It will not affect the result of what will be deployed. 
However the generation of diagrams may not work very consistent.


## Class Diagrams

Add following snippet to your model:

```inmanta
graph::ClassDiagram(name="my_diagram", moduleexpression=["std::.*"], header="""
skinparam monochrome true
skinparam shadowing false
set namespaceSeparator ::
left to right direction""")
```

then export using 

```bash
inmanta -vv export  -j x.json --export-plugin=classdiagram
plantuml my_diagram.puml -tsvg
```

This will produce a class diagram for the module 'std'.

# Diagram definition
Add following snippet to your model:

```inmanta
graph::Graph(name="my_graph", config=std::source("/files_and_hosts.g"))
```

Add the graph filter file `./files/files_and_hosts.g`
```
std::Host
std::File
std::File.host
```

This will filter all `std::Host` and `std::File` instance out of the model and add them to the graph. 
The statement `std::File.host` will add all the `host` relations of all the files to the graph as well. 

to generate the graph

```bash
inmanta -vv export  -j x.json --export-plugin=graph
```

This will create a file `my_graph.dot` and `my_graph.png`


# Documentation

## Settings

The plugin has settings that can be added to the inmanta config file (.inmanta or other specified). All settings are set in the
[graph] section.

- output-dir: The location where all the generated graphs are stored.
- types: A list of file types that should be generated. By default a png is generated. This list can contain multiple values
         separated with commas. If only the dot file is required an empty value should be provided.

## Graph Filter format 

Each line of the graph filter can contain 
 1. empty lines
 2. comments (start with `#`),
 3. an entity type with optional settings
 4. relation definitions with optional settings. 
 
The exporter selects both the entity instances and relations between these
instances to show in a diagram.

### Entity type 

Select all instance of a certain entity by specifying the full name of the type.

Between square brackets options can be specified:
    - label: The label of the instances. It can be either an attribute of the entity or a string indicated with double
             quotes. This string can contain formatters between curly braces {}. Between these braces name of the attributes
             can be used.
    - container: If set to true, this node will be treated as a container that can contain other nodes. See, type=contained_in

For example:
```
std::File[label=path]
std::Service[label="Service name {name}"]
```

### Entity relations

With the full name of the entity and the name of the relation, edges between instances are added to the graph.

Between square brackets options can be specified:
    - label: The label on the edge. Either the name of the attribute when nothing is specified or a string with double quotes.
    - type: This can changes the relation type. The options are:
        * contained_in: This means that this relation indicates that the node should be placed inside the target node of the
                        relation.

For example:
```
std::File.host[type=contained_in]
std::Host[shape=box, container=true]
```
