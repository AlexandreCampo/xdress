"""
Filters parsed code to exclude methods or attributes that have certain
types as input parameters.

This module is available as the xdress plugin ``xdress.typefilter``.

:author: Spencer Lyon <spencerlyon2@gmail.com>

Type Filtering
==============

This plugin alters the description dictionary generated by other xdress
plugins (mainly ``xdress.autoall`` and ``xdress.autodescribe``) by
removing attributes or methods that contain argument types the user
wishes to exclude from the generated cython wrapper. To use
``xdress.typefilter``, you need to do two things in the xdressrc file
for your project.

1. Add it to the list of plugins
2. Define the ``skiptpyes`` list or dictionary. If ``skiptypes`` is a
dictionary the keys are class names and the values are lists (or tuples)
of data types that should be left out of the generated code for the
class. If ``skiptypes`` is a list or tuple, the skipped types will be
applied to all classes listed in the ``classes`` list in xdressrc. If
``skiptypes`` is empty or ``None`` this plugin will do nothing.

This might be done with something like:

    plugins = ('xdress.stlwrap', 'xdress.autoall', 'xdress.autodescribe',
               'xdress.typefilter', 'xdress.cythongen')

    # Later in the xdressrc
    skiptypes = {'classA': ['float64', (('int32', 'const'), '&')],
                 'classB': ['classA', ('vector', 'float32')]}

.. warning::

    Notice that ``xdress.typefilter`` comes after ``xdress.autoall``,
    and ``xdress.autodescribe`` but before ``xdress.cythongen``. This is
    necessary because the description dictionary needs to be populated
    by autoall and autodescribe, but the type filter needs to be applied
    before any code is generated by cythongen.

I also could have done the following to exclude all instances of
particular types, regardless of the class in which they arise.

    skiptypes = ['uint32', (('vector', 'float64', 'const'), '&')]

A Closer Look
=============

As of right now ``xdress.typefilter`` is set up to handle skiptype
elements of two flavors.

1. A single type identifier. This could be any base type,  (e.g. int32,
char, float64, ect), an STL type (e.g. vector, map, set), or any type
xdress knows about (like classA in the first example above). In this
case xdress will flatten all argument types and if the single type
identifier appears anywhere in the flattened argument description, the
method will be filtered out.

For example, if 'float64' were in the ``skiptypes`` it would catch any
of the following argument types (this is by no means a complete list):

    "float64"
    (('vector', 'float64', 'const'), '&')
    ('set', 'float64')

2. A specific argument or return type that will match exactly. This
option provides more control over what ``xdress.typefilter`` will catch
and can prevent the plugin from being to ambitious with regards to the
methods that are filtered out.

Typically, the first option would be used in situations where xdress,
for whatever reason, cannot create a wrapper for a user-defined C++
class. This might happen due to limitations with xdress itself, or
perhaps limitations with Cython.

Users are advised to use the second option in most other circumstances
in order to forestall any potential issues with needed methods not
being wrapped.

"""
from __future__ import print_function
from .utils import isclassdesc, NotSpecified
from .typesystem import TypeMatcher
from .plugins import Plugin


def _flatten(iterable):
    "Recursive hack to flatten arbitrary lists/tuples of lists/tuples"
    res = []
    try:
        for el in iterable:
            if isinstance(el, (list, tuple)):
                res.extend(_flatten(el))
                continue
            res.append(el)
    except TypeError:
        res = iterable
    return res


def _match_anywhere(self, t):
    "To be monkey-patched into TypeMatcher"
    try:
        # See if user gave entire type
        if self.matches(t):
            return True
    except TypeError:
        # This might fail, if it does just move on
        pass

    else:
        if isinstance(t, str):
            return self.matches(t)
        elif isinstance(t, (tuple, list)):
            return any([self.matches(i) for i in _flatten(t)])

TypeMatcher._match_anywhere = _match_anywhere


class XDressPlugin(Plugin):

    requires = ('xdress.base', 'xdress.autoall')

    defaultrc = {'skiptypes': NotSpecified}

    def setup(self, rc):
        if not isinstance(rc.skiptypes, NotSpecified):

            # Update dict so everything is a TypeMatcher instance
            if isinstance(rc.skiptypes, dict):
                _skippers = {}
                for kls in rc.skiptypes.keys():
                    _skippers[kls] = [TypeMatcher(t) for t in rc.skiptypes[kls]]

                rc.skiptypes = _skippers

            # Update tuple or list to be full of TypeMatchers
            elif isinstance(rc.skiptypes, list) or isinstance(rc.skiptypes,
                                                              tuple):
                rc.skiptypes = [TypeMatcher(t) for t in rc.skiptypes]
                print(rc.skiptypes)

    def execute(self, rc):
        print("typefilter: removing unwanted types from desc dictionary")
        if not isinstance(rc.skiptypes, NotSpecified):
            if isinstance(rc.skiptypes, dict):
                skip_classes = rc.skiptypes.keys()
                for mod_key, mod in rc.env.items():
                    for kls_key, desc in mod.items():
                        if isclassdesc(desc):
                            if desc['name'] in skip_classes:
                                rc.env[mod_key][kls_key] = \
                                    self._modify_class_desc(rc, desc,
                                                            name=desc['name'])

            elif isinstance(rc.skiptypes, list):
                for mod in rc.env.values():
                    for desc in mod.values():
                        if isclassdesc(desc):
                            self._modify_class_desc(rc, desc)

    def _modify_class_desc(self, rc, desc, name=None):
        if name is None:
            skips = rc.skiptypes
        else:
            skips = rc.skiptypes[name]

        # remove attrs with bad types
        for at_name, at_t in desc['attrs'].copy().items():
            for tm in skips:
                if tm._match_anywhere(at_t):
                    del desc['attrs'][at_name]
                    break

        # remove methods with bad parameter types or return types
        for m_key, m_ret in desc['methods'].copy().items():
            _deleted = False
            # Check return types
            for tm in skips:
                if tm._match_anywhere(m_ret):
                    del desc['methods'][m_key]
                    _deleted = True
                    break

            # Stop here if we already got it
            if _deleted:
                continue

            m_args = m_key[1:]

            for arg in m_args:
                t = arg[1]  # Just use type, not parameter name or default val
                for tm in skips:
                    # c1 = tm._match_anywhere(t)
                    # c2 =
                    if tm._match_anywhere(t):
                        del desc['methods'][m_key]
                        _deleted = True
                        break

                if _deleted:
                    break

        return desc
