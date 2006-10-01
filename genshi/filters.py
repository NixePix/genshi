# -*- coding: utf-8 -*-
#
# Copyright (C) 2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://genshi.edgewall.org/wiki/License.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://genshi.edgewall.org/log/.

"""Implementation of a number of stream filters."""

try:
    frozenset
except NameError:
    from sets import ImmutableSet as frozenset
import re

from genshi.core import Attrs, Namespace, stripentities
from genshi.core import END, END_NS, START, START_NS, TEXT

__all__ = ['HTMLFormFiller', 'HTMLSanitizer', 'IncludeFilter']


class HTMLFormFiller(object):
    """A stream filter that can populate HTML forms from a dictionary of values.
    
    >>> from genshi.input import HTML
    >>> html = HTML('''<form>
    ...   <p><input type="text" name="foo" /></p>
    ... </form>''')
    >>> filler = HTMLFormFiller(data={'foo': 'bar'})
    >>> print html | filler
    <form>
      <p><input type="text" name="foo" value="bar"/></p>
    </form>
    """
    # TODO: only select the first radio button, and the first select option
    #       (if not in a multiple-select)
    # TODO: only apply to elements in the XHTML namespace (or no namespace)?

    def __init__(self, name=None, id=None, data=None):
        """Create the filter.
        
        @param name: The name of the form that should be populated. If this
            parameter is given, only forms where the ``name`` attribute value
            matches the parameter are processed.
        @param id: The ID of the form that should be populated. If this
            parameter is given, only forms where the ``id`` attribute value
            matches the parameter are processed.
        @param data: The dictionary of form values, where the keys are the names
            of the form fields, and the values are the values to fill in.
        """
        self.name = name
        self.id = id
        if data is None:
            data = {}
        self.data = data

    def __call__(self, stream, ctxt=None):
        """Apply the filter to the given stream."""
        in_form = in_select = in_option = in_textarea = False
        select_value = option_value = textarea_value = None
        option_start = option_text = None

        for kind, data, pos in stream:

            if kind is START:
                tag, attrib = data
                tagname = tag.localname

                if tagname == 'form' and (
                        self.name and attrib.get('name') == self.name or
                        self.id and attrib.get('id') == self.id or
                        not (self.id or self.name)):
                    in_form = True

                elif in_form:
                    if tagname == 'input':
                        type = attrib.get('type')
                        if type in ('checkbox', 'radio'):
                            name = attrib.get('name')
                            if name:
                                value = self.data.get(name)
                                declval = attrib.get('value')
                                checked = False
                                if isinstance(value, (list, tuple)):
                                    if declval:
                                        checked = declval in value
                                    else:
                                        checked = bool(filter(None, value))
                                else:
                                    if declval:
                                        checked = declval == value
                                    elif type == 'checkbox':
                                        checked = bool(value)
                                if checked:
                                    attrib.set('checked', 'checked')
                                else:
                                    attrib.remove('checked')
                        elif type in (None, 'hidden', 'text'):
                            name = attrib.get('name')
                            if name:
                                value = self.data.get(name)
                                if isinstance(value, (list, tuple)):
                                    value = value[0]
                                if value is not None:
                                    attrib.set('value', unicode(value))
                    elif tagname == 'select':
                        name = attrib.get('name')
                        select_value = self.data.get(name)
                        in_select = True
                    elif tagname == 'textarea':
                        name = attrib.get('name')
                        textarea_value = self.data.get(name)
                        if isinstance(textarea_value, (list, tuple)):
                            textarea_value = textarea_value[0]
                        in_textarea = True
                    elif in_select and tagname == 'option':
                        option_start = kind, data, pos
                        option_value = attrib.get('value')
                        in_option = True
                        continue

            elif in_form and kind is TEXT:
                if in_select and in_option:
                    if option_value is None:
                        option_value = data
                    option_text = kind, data, pos
                    continue
                elif in_textarea:
                    continue

            elif in_form and kind is END:
                tagname = data.localname
                if tagname == 'form':
                    in_form = False
                elif tagname == 'select':
                    in_select = False
                    select_value = None
                elif in_select and tagname == 'option':
                    if isinstance(select_value, (tuple, list)):
                        selected = option_value in select_value
                    else:
                        selected = option_value == select_value
                    attrib = option_start[1][1]
                    if selected:
                        attrib.set('selected', 'selected')
                    else:
                        attrib.remove('selected')
                    yield option_start
                    if option_text:
                        yield option_text
                    in_option = False
                    option_start = option_text = option_value = None
                elif tagname == 'textarea':
                    if textarea_value:
                        yield TEXT, unicode(textarea_value), pos
                    in_textarea = False

            yield kind, data, pos


class HTMLSanitizer(object):
    """A filter that removes potentially dangerous HTML tags and attributes
    from the stream.
    """

    _SAFE_TAGS = frozenset(['a', 'abbr', 'acronym', 'address', 'area', 'b',
        'big', 'blockquote', 'br', 'button', 'caption', 'center', 'cite',
        'code', 'col', 'colgroup', 'dd', 'del', 'dfn', 'dir', 'div', 'dl', 'dt',
        'em', 'fieldset', 'font', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'hr', 'i', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'map',
        'menu', 'ol', 'optgroup', 'option', 'p', 'pre', 'q', 's', 'samp',
        'select', 'small', 'span', 'strike', 'strong', 'sub', 'sup', 'table',
        'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u',
        'ul', 'var'])

    _SAFE_ATTRS = frozenset(['abbr', 'accept', 'accept-charset', 'accesskey',
        'action', 'align', 'alt', 'axis', 'bgcolor', 'border', 'cellpadding',
        'cellspacing', 'char', 'charoff', 'charset', 'checked', 'cite', 'class',
        'clear', 'cols', 'colspan', 'color', 'compact', 'coords', 'datetime',
        'dir', 'disabled', 'enctype', 'for', 'frame', 'headers', 'height',
        'href', 'hreflang', 'hspace', 'id', 'ismap', 'label', 'lang',
        'longdesc', 'maxlength', 'media', 'method', 'multiple', 'name',
        'nohref', 'noshade', 'nowrap', 'prompt', 'readonly', 'rel', 'rev',
        'rows', 'rowspan', 'rules', 'scope', 'selected', 'shape', 'size',
        'span', 'src', 'start', 'style', 'summary', 'tabindex', 'target',
        'title', 'type', 'usemap', 'valign', 'value', 'vspace', 'width'])
    _URI_ATTRS = frozenset(['action', 'background', 'dynsrc', 'href', 'lowsrc',
        'src'])
    _SAFE_SCHEMES = frozenset(['file', 'ftp', 'http', 'https', 'mailto', None])

    def __call__(self, stream, ctxt=None):
        waiting_for = None

        for kind, data, pos in stream:
            if kind is START:
                if waiting_for:
                    continue
                tag, attrib = data
                if tag not in self._SAFE_TAGS:
                    waiting_for = tag
                    continue

                new_attrib = Attrs()
                for attr, value in attrib:
                    value = stripentities(value)
                    if attr not in self._SAFE_ATTRS:
                        continue
                    elif attr in self._URI_ATTRS:
                        # Don't allow URI schemes such as "javascript:"
                        if self._get_scheme(value) not in self._SAFE_SCHEMES:
                            continue
                    elif attr == 'style':
                        # Remove dangerous CSS declarations from inline styles
                        decls = []
                        for decl in filter(None, value.split(';')):
                            is_evil = False
                            if 'expression' in decl:
                                is_evil = True
                            for m in re.finditer(r'url\s*\(([^)]+)', decl):
                                if self._get_scheme(m.group(1)) not in self._SAFE_SCHEMES:
                                    is_evil = True
                                    break
                            if not is_evil:
                                decls.append(decl.strip())
                        if not decls:
                            continue
                        value = '; '.join(decls)
                    new_attrib.append((attr, value))

                yield kind, (tag, new_attrib), pos

            elif kind is END:
                tag = data
                if waiting_for:
                    if waiting_for == tag:
                        waiting_for = None
                else:
                    yield kind, data, pos

            else:
                if not waiting_for:
                    yield kind, data, pos

    def _get_scheme(self, text):
        if ':' not in text:
            return None
        chars = [char for char in text.split(':', 1)[0] if char.isalnum()]
        return ''.join(chars).lower()


class IncludeFilter(object):
    """Template filter providing (very) basic XInclude support
    (see http://www.w3.org/TR/xinclude/) in templates.
    """

    NAMESPACE = Namespace('http://www.w3.org/2001/XInclude')

    def __init__(self, loader):
        """Initialize the filter.
        
        @param loader: the `TemplateLoader` to use for resolving references to
            external template files
        """
        self.loader = loader

    def __call__(self, stream, ctxt=None):
        """Filter the stream, processing any XInclude directives it may
        contain.
        
        @param stream: the markup event stream to filter
        @param ctxt: the template context
        """
        from genshi.template import TemplateError, TemplateNotFound

        ns_prefixes = []
        in_fallback = False
        include_href, fallback_stream = None, None
        namespace = self.NAMESPACE

        for kind, data, pos in stream:

            if kind is START and not in_fallback and data[0] in namespace:
                tag, attrib = data
                if tag.localname == 'include':
                    include_href = attrib.get('href')
                elif tag.localname == 'fallback':
                    in_fallback = True
                    fallback_stream = []

            elif kind is END and data in namespace:
                if data.localname == 'include':
                    try:
                        if not include_href:
                            raise TemplateError('Include misses required '
                                                'attribute "href"')
                        template = self.loader.load(include_href,
                                                    relative_to=pos[0])
                        for event in template.generate(ctxt):
                            yield event

                    except TemplateNotFound:
                        if fallback_stream is None:
                            raise
                        for event in fallback_stream:
                            yield event

                    include_href = None
                    fallback_stream = None

                elif data.localname == 'fallback':
                    in_fallback = False

            elif in_fallback:
                fallback_stream.append((kind, data, pos))

            elif kind is START_NS and data[1] == namespace:
                ns_prefixes.append(data[0])

            elif kind is END_NS and data in ns_prefixes:
                ns_prefixes.pop()

            else:
                yield kind, data, pos
