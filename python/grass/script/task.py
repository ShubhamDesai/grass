"""
Get interface description of GRASS commands

Based on gui/wxpython/gui_modules/menuform.py

Usage:

::

    from grass.script import task as gtask

    gtask.command_info("r.info")

(C) 2011 by the GRASS Development Team
This program is free software under the GNU General Public
License (>=v2). Read the file COPYING that comes with GRASS
for details.

.. sectionauthor:: Martin Landa <landa.martin gmail.com>
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.parsers import expat

from grass.exceptions import ScriptError
from .utils import decode, split
from .core import Popen, PIPE, get_real_command

ETREE_EXCEPTIONS = (ET.ParseError, expat.ExpatError)


class grassTask:
    """This class holds the structures needed for filling by the parser

    Parameter blackList is a dictionary with fixed structure, eg.

    ::

        blackList = {
            "items": {"d.legend": {"flags": ["m"], "params": []}},
            "enabled": True,
        }

    :param str path: full path
    :param blackList: hide some options in the GUI (dictionary)
    """

    def __init__(self, path=None, blackList=None):
        self.path = path
        self.name = _("unknown")
        self.params = []
        self.description = ""
        self.label = ""
        self.flags = []
        self.keywords = []
        self.errorMsg = ""
        self.firstParam = None
        if blackList:
            self.blackList = blackList
        else:
            self.blackList = {"enabled": False, "items": {}}

        if path is not None:
            try:
                processTask(
                    tree=ET.fromstring(get_interface_description(path)), task=self
                )
            except ScriptError as e:
                self.errorMsg = e.value

            self.define_first()

    def define_first(self):
        """Define first parameter

        :return: name of first parameter
        """
        if len(self.params) > 0:
            self.firstParam = self.params[0]["name"]

        return self.firstParam

    def get_error_msg(self):
        """Get error message ('' for no error)"""
        return self.errorMsg

    def get_name(self):
        """Get task name"""
        if sys.platform != "win32":
            return self.name

        name, ext = os.path.splitext(self.name)
        if ext in {".py", ".sh"}:
            return name
        return self.name

    def get_description(self, full=True):
        """Get module's description

        :param bool full: True for label + desc
        """
        if not self.label:
            return self.description
        if full:
            return self.label + " " + self.description
        return self.label

    def get_keywords(self):
        """Get module's keywords"""
        return self.keywords

    def get_list_params(self, element="name"):
        """Get list of parameters

        :param str element: element name
        """
        return [p[element] for p in self.params]

    def get_list_flags(self, element="name"):
        """Get list of flags

        :param str element: element name
        """
        return [p[element] for p in self.flags]

    def get_param(self, value, element="name", raiseError=True):
        """Find and return a param by name

        :param value: param's value
        :param str element: element name
        :param bool raiseError: True for raise on error
        """
        for p in self.params:
            val = p.get(element, None)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                if value in val:
                    return p
            elif p[element] == value:
                return p

        if raiseError:
            raise ValueError(
                _("Parameter element '%(element)s' not found: '%(value)s'")
                % {"element": element, "value": value}
            )
        return None

    def get_flag(self, aFlag):
        """Find and return a flag by name

        Raises ValueError when the flag is not found.

        :param str aFlag: name of the flag
        :raises ValueError: When the flag is not found.
        """
        for f in self.flags:
            if f["name"] == aFlag:
                return f
        raise ValueError(_("Flag not found: %s") % aFlag)

    def get_cmd_error(self) -> list[str]:
        """Get error string produced by get_cmd(ignoreErrors = False)

        :return: list of errors
        """
        errorList = []
        # determine if suppress_required flag is given
        for f in self.flags:
            if f["value"] and f["suppress_required"]:
                return errorList

        for p in self.params:
            if not p.get("value", "") and p.get("required", False):
                if not p.get("default", ""):
                    desc = p.get("label", "")
                    if not desc:
                        desc = p["description"]
                    errorList.append(
                        _("Parameter '%(name)s' (%(desc)s) is missing.")
                        % {"name": p["name"], "desc": desc}
                    )

        return errorList

    def get_cmd(self, ignoreErrors=False, ignoreRequired=False, ignoreDefault=True):
        """Produce an array of command name and arguments for feeding
        into some execve-like command processor.

        :param bool ignoreErrors: True to return whatever has been built so
                                  far, even though it would not be a correct
                                  command for GRASS
        :param bool ignoreRequired: True to ignore required flags, otherwise
                                    '@<required@>' is shown
        :param bool ignoreDefault: True to ignore parameters with default values

        :raises ValueError: When ``ignoreErrors=False`` and there are errors
        """
        cmd = [self.get_name()]

        suppress_required = False
        for flag in self.flags:
            if flag["value"]:
                if len(flag["name"]) > 1:  # e.g. overwrite
                    cmd += ["--" + flag["name"]]
                else:
                    cmd += ["-" + flag["name"]]
                if flag["suppress_required"]:
                    suppress_required = True
        for p in self.params:
            if p.get("value", "") == "" and p.get("required", False):
                if p.get("default", "") != "":
                    cmd += ["%s=%s" % (p["name"], p["default"])]
                elif ignoreErrors and not suppress_required and not ignoreRequired:
                    cmd += ["%s=%s" % (p["name"], _("<required>"))]
            elif (
                p.get("value", "") == ""
                and p.get("default", "") != ""
                and not ignoreDefault
            ):
                cmd += ["%s=%s" % (p["name"], p["default"])]
            elif p.get("value", "") != "" and (
                p["value"] != p.get("default", "") or not ignoreDefault
            ):
                # output only values that have been set, and different from defaults
                cmd += ["%s=%s" % (p["name"], p["value"])]

        errList = self.get_cmd_error()
        if ignoreErrors is False and errList:
            raise ValueError("\n".join(errList))

        return cmd

    def get_options(self):
        """Get options"""
        return {"flags": self.flags, "params": self.params}

    def has_required(self):
        """Check if command has at least one required parameter"""
        return any(p.get("required", False) for p in self.params)

    def set_param(self, aParam, aValue, element="value"):
        """Set param value/values."""
        try:
            param = self.get_param(aParam)
        except ValueError:
            return

        param[element] = aValue

    def set_flag(self, aFlag, aValue, element="value"):
        """Enable / disable flag."""
        try:
            param = self.get_flag(aFlag)
        except ValueError:
            return

        param[element] = aValue

    def set_options(self, opts):
        """Set flags and parameters

        :param opts list of flags and parameters"""
        for opt in opts:
            if opt[0] == "-":  # flag
                self.set_flag(opt.lstrip("-"), True)
            else:  # parameter
                key, value = opt.split("=", 1)
                self.set_param(key, value)


class processTask:
    """A ElementTree handler for the --interface-description output,
    as defined in grass-interface.dtd. Extend or modify this and the
    DTD if the XML output of GRASS' parser is extended or modified.

    :param tree: root tree node
    :param task: grassTask instance or None
    :param blackList: list of flags/params to hide

    :return: grassTask instance
    """

    def __init__(self, tree, task=None, blackList=None):
        if task:
            self.task = task
        else:
            self.task = grassTask()
        if blackList:
            self.task.blackList = blackList

        self.root = tree

        self._process_module()
        self._process_params()
        self._process_flags()
        self.task.define_first()

    def _process_module(self):
        """Process module description"""
        self.task.name = self.root.get("name", default="unknown")

        # keywords
        for keyword in self._get_node_text(self.root, "keywords").split(","):
            self.task.keywords.append(keyword.strip())

        self.task.label = self._get_node_text(self.root, "label")
        self.task.description = self._get_node_text(self.root, "description")

    def _process_params(self) -> None:
        """Process parameters"""
        for p in self.root.findall("parameter"):
            # gisprompt
            node_gisprompt = p.find("gisprompt")
            gisprompt = False
            age = element = prompt = None
            if node_gisprompt is not None:
                gisprompt = True
                age = node_gisprompt.get("age", "")
                element = node_gisprompt.get("element", "")
                prompt = node_gisprompt.get("prompt", "")

            # value(s)
            values = []
            values_desc = []
            node_values = p.find("values")
            if node_values is not None:
                for pv in node_values.findall("value"):
                    values.append(self._get_node_text(pv, "name"))
                    desc = self._get_node_text(pv, "description")
                    if desc:
                        values_desc.append(desc)

            # keydesc
            key_desc = []
            node_key_desc = p.find("keydesc")
            if node_key_desc is not None:
                for ki in node_key_desc.findall("item"):
                    key_desc.append(ki.text)

            multiple = p.get("multiple", "no") == "yes"
            required = p.get("required", "no") == "yes"

            hidden: bool = bool(
                self.task.blackList["enabled"]
                and self.task.name in self.task.blackList["items"]
                and p.get("name")
                in self.task.blackList["items"][self.task.name].get("params", [])
            )

            self.task.params.append(
                {
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "required": required,
                    "multiple": multiple,
                    "label": self._get_node_text(p, "label"),
                    "description": self._get_node_text(p, "description"),
                    "gisprompt": gisprompt,
                    "age": age,
                    "element": element,
                    "prompt": prompt,
                    "guisection": self._get_node_text(p, "guisection"),
                    "guidependency": self._get_node_text(p, "guidependency"),
                    "default": self._get_node_text(p, "default"),
                    "values": values,
                    "values_desc": values_desc,
                    "value": "",
                    "key_desc": key_desc,
                    "hidden": hidden,
                }
            )

    def _process_flags(self) -> None:
        """Process flags"""
        for p in self.root.findall("flag"):
            hidden: bool = bool(
                self.task.blackList["enabled"]
                and self.task.name in self.task.blackList["items"]
                and p.get("name")
                in self.task.blackList["items"][self.task.name].get("flags", [])
            )

            suppress_required: bool = bool(p.find("suppress_required") is not None)

            self.task.flags.append(
                {
                    "name": p.get("name"),
                    "label": self._get_node_text(p, "label"),
                    "description": self._get_node_text(p, "description"),
                    "guisection": self._get_node_text(p, "guisection"),
                    "suppress_required": suppress_required,
                    "value": False,
                    "hidden": hidden,
                }
            )

    def _get_node_text(self, node, tag, default=""):
        """Get node text"""
        p = node.find(tag)
        if p is not None:
            return " ".join(p.text.split())

        return default

    def get_task(self):
        """Get grassTask instance"""
        return self.task


def convert_xml_to_utf8(xml_text):
    # enc = locale.getdefaultlocale()[1]
    if xml_text is None:
        return None
    # modify: fetch encoding from the interface description text(xml)
    # e.g. <?xml version="1.0" encoding="GBK"?>
    pattern = re.compile(rb'<\?xml[^>]*\Wencoding="([^"]*)"[^>]*\?>')
    m = re.match(pattern, xml_text)
    if m is None:
        try:
            xml_text.decode("utf-8", errors="strict")
            return xml_text
        except UnicodeDecodeError:
            return decode(xml_text).encode("utf-8")

    enc = m.groups()[0]

    # modify: change the encoding to "utf-8", for correct parsing
    xml_text_utf8 = xml_text.decode(enc.decode("ascii")).encode("utf-8")
    p = re.compile(b'encoding="' + enc + b'"', re.IGNORECASE)
    return p.sub(b'encoding="utf-8"', xml_text_utf8)


def get_interface_description(cmd):
    """Returns the XML description for the GRASS cmd (force text encoding to
    "utf-8").

    The DTD must be located in $GISBASE/gui/xml/grass-interface.dtd,
    otherwise the parser will not succeed.

    :param cmd: command (name of GRASS module)
    :raises ~grass.exceptions.ScriptError:
        When unable to fetch the interface description for a command.
    """
    try:
        p = Popen(
            [cmd, "--interface-description"], stdout=PIPE, stderr=PIPE, text=False
        )
        cmdout, cmderr = p.communicate()

        # TODO: do it better (?)
        if not cmdout and sys.platform == "win32":
            # we in fact expect pure module name (without extension)
            # so, lets remove extension
            if cmd.endswith(".py"):
                cmd = os.path.splitext(cmd)[0]

            if cmd == "d.rast3d":
                sys.path.insert(0, os.path.join(os.getenv("GISBASE"), "gui", "scripts"))

            p = Popen(
                [sys.executable, get_real_command(cmd), "--interface-description"],
                stdout=PIPE,
                stderr=PIPE,
                text=False,
            )
            cmdout, cmderr = p.communicate()

            if cmd == "d.rast3d":
                del sys.path[0]  # remove gui/scripts from the path

        if p.returncode != 0:
            raise ScriptError(
                _(
                    "Unable to fetch interface description for command '<{cmd}>'."
                    "\n\nDetails: <{det}>"
                ).format(cmd=cmd, det=decode(cmderr))
            )

    except OSError as e:
        raise ScriptError(
            _(
                "Unable to fetch interface description for command '<{cmd}>'."
                "\n\nDetails: <{det}>"
            ).format(cmd=cmd, det=e)
        )

    desc = convert_xml_to_utf8(cmdout)
    return desc.replace(
        b"grass-interface.dtd",
        os.path.join(os.getenv("GISBASE"), "gui", "xml", "grass-interface.dtd").encode(
            "utf-8"
        ),
    )


def parse_interface(name, parser=processTask, blackList=None):
    """Parse interface of given GRASS module

    The *name* is either GRASS module name (of a module on path) or
    a full or relative path to an executable.

    :param str name: name of GRASS module to be parsed
    :param parser:
    :param blackList:

    :raises ~grass.exceptions.ScriptError:
        When the interface description of a module cannot be parsed.
    """
    try:
        tree = ET.fromstring(get_interface_description(name))
    except ETREE_EXCEPTIONS as error:
        raise ScriptError(
            _("Cannot parse interface description of <{name}> module: {error}").format(
                name=name, error=error
            )
        )
    task = parser(tree, blackList=blackList).get_task()
    # if name from interface is different than the originally
    # provided name, then the provided name is likely a full path needed
    # to actually run the module later
    # (processTask uses only the XML which does not contain the original
    # path used to execute the module)
    if task.name != name:
        task.path = name
    return task


def command_info(cmd):
    """Returns meta information for any GRASS command as dictionary
    with entries for description, keywords, usage, flags, and
    parameters, e.g.

    >>> command_info("g.tempfile")  # doctest: +NORMALIZE_WHITESPACE
    {'keywords': ['general', 'support'], 'params': [{'gisprompt': False,
    'multiple': False, 'name': 'pid', 'guidependency': '', 'default': '',
    'age': None, 'required': True, 'value': '', 'label': '', 'guisection': '',
    'key_desc': [], 'values': [], 'values_desc': [], 'prompt': None,
    'hidden': False, 'element': None, 'type': 'integer', 'description':
    'Process id to use when naming the tempfile'}], 'flags': [{'description':
    "Dry run - don't create a file, just prints it's file name", 'value':
    False, 'label': '', 'guisection': '', 'suppress_required': False,
    'hidden': False, 'name': 'd'}, {'description': 'Print usage summary',
    'value': False, 'label': '', 'guisection': '', 'suppress_required': False,
    'hidden': False, 'name': 'help'}, {'description': 'Verbose module output',
    'value': False, 'label': '', 'guisection': '', 'suppress_required': False,
    'hidden': False, 'name': 'verbose'}, {'description': 'Quiet module output',
    'value': False, 'label': '', 'guisection': '', 'suppress_required': False,
    'hidden': False, 'name': 'quiet'}], 'description': "Creates a temporary
    file and prints it's file name.", 'usage': 'g.tempfile pid=integer [--help]
    [--verbose] [--quiet]'}

    >>> command_info("v.buffer")
    ['vector', 'geometry', 'buffer']

    :param str cmd: the command to query
    """
    task = parse_interface(cmd)
    flags = task.get_options()["flags"]
    params = task.get_options()["params"]
    cmdinfo = {
        "description": task.get_description(),
        "keywords": task.get_keywords(),
        "flags": flags,
        "params": params,
    }

    usage = task.get_name()
    flags_short = []
    flags_long = []
    for f in flags:
        fname = f.get("name", "unknown")
        if len(fname) > 1:
            flags_long.append(fname)
        else:
            flags_short.append(fname)

    if len(flags_short) > 1:
        usage += " [-" + "".join(flags_short) + "]"

    for p in params:
        ptype = ",".join(p.get("key_desc", []))
        if not ptype:
            ptype = p.get("type", "")
        req = p.get("required", False)
        if not req:
            usage += " ["
        else:
            usage += " "
        usage += p["name"] + "=" + ptype
        if p.get("multiple", False):
            usage += "[," + ptype + ",...]"
        if not req:
            usage += "]"

    for key in flags_long:
        usage += " [--" + key + "]"

    cmdinfo["usage"] = usage

    return cmdinfo


def cmdtuple_to_list(cmd):
    """Convert command tuple to list.

    :param tuple cmd: GRASS command to be converted

    :return: command in list
    """
    cmdList = []
    if not cmd:
        return cmdList

    cmdList.append(cmd[0])

    if "flags" in cmd[1]:
        for flag in cmd[1]["flags"]:
            cmdList.append("-" + flag)
    for flag in ("help", "verbose", "quiet", "overwrite"):
        if flag in cmd[1] and cmd[1][flag] is True:
            cmdList.append("--" + flag)

    for k, v in cmd[1].items():
        if k in {"flags", "help", "verbose", "quiet", "overwrite"}:
            continue
        if " " in v:
            v = '"%s"' % v
        cmdList.append("%s=%s" % (k, v))

    return cmdList


def cmdlist_to_tuple(cmd):
    """Convert command list to tuple for run_command() and others

    :param list cmd: GRASS command to be converted

    :return: command as tuple
    """
    if len(cmd) < 1:
        return None

    dcmd = {}
    for item in cmd[1:]:
        if "=" in item:  # params
            key, value = item.split("=", 1)
            dcmd[str(key)] = value.replace('"', "")
        elif item[:2] == "--":  # long flags
            flag = item[2:]
            if flag in {"help", "verbose", "quiet", "overwrite"}:
                dcmd[str(flag)] = True
        elif len(item) == 2 and item[0] == "-":  # -> flags
            if "flags" not in dcmd:
                dcmd["flags"] = ""
            dcmd["flags"] += item[1]
        else:  # unnamed parameter
            module = parse_interface(cmd[0])
            dcmd[module.define_first()] = item

    return (cmd[0], dcmd)


def cmdstring_to_tuple(cmd):
    """Convert command string to tuple for run_command() and others

    :param str cmd: command to be converted

    :return: command as tuple
    """
    return cmdlist_to_tuple(split(cmd))
