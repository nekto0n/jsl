# coding: utf-8
import re
import sre_constants

from . import registry
from .roles import maybe_resolve, maybe_resolve_2, DEFAULT_ROLE, maybe_resolve_all_roles
from .scope import ResolutionScope
from ._compat import iteritems, iterkeys, itervalues, string_types, OrderedDict


RECURSIVE_REFERENCE_CONSTANT = 'self'


def _validate_regex(regex):
    """
    :type regex: str
    :raises: ValueError
    :return:
    """
    try:
        re.compile(regex)
    except sre_constants.error as e:
        raise ValueError('Invalid regular expression: {0}'.format(e))


class BaseField(object):
    """A base class for fields in a JSL :class:`.document.Document`.
    Instances of this class may be added to a document to define its properties.

    :param required:
        If the field is required, defaults to False.
    """

    def __init__(self, required=False):
        self.required = required

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(),
                                   ordered=False, ref_documents=None):  # pragma: no cover
        """Returns a tuple of two elements.

        The second element is a JSON schema of the data described by this field,
        and the first is a dictionary containing definitions that are referenced
        from the field schema.

        :arg role:
            A role. TODO
        :type role: string
        :arg ordered:
            If True, the resulting schema is an OrderedDict and its properties are ordered
            in a sensible way, which makes it more readable.
        :type ordered: bool
        :arg scope:
            Current resolution scope.
        :type scope: :class:`.scope.ResolutionScope`
        :arg ref_documents:
            If subclass of :class:`Document` is in this set, all :class:`DocumentField` s
            pointing to it will be resolved to a reference: ``{"$ref": "#/definitions/..."}``.
            Note: resulting definitions will not contain schema for this document.
        :type ref_documents: set
        :rtype: (dict, dict)
        """
        raise NotImplementedError()

    def get_schema(self, ordered=False, role=DEFAULT_ROLE):
        """Returns a JSON schema (draft v4) of the data described by this field.

        :arg role:
            A role. TODO
        :type role: string
        :arg ordered:
            If True, the resulting schema is an OrderedDict and its properties are ordered
            in a sensible way, which makes it more readable.
        :type ordered: bool
        """
        definitions, schema = self.get_definitions_and_schema(ordered=ordered, role=role)
        if definitions:
            schema['definitions'] = definitions
        return schema

    def iter_fields(self, role=DEFAULT_ROLE):
        return iter([])

    def walk(self, role=DEFAULT_ROLE, through_document_fields=False, visited_documents=frozenset()):
        """Yields nested fields in a DFS order."""
        yield self
        for field in self.iter_fields(role=role):
            field, field_role = maybe_resolve_2(field, role)
            if field is None:
                continue
            for field_ in field.walk(role=field_role,
                                     through_document_fields=through_document_fields,
                                     visited_documents=visited_documents):
                yield field_


class BaseSchemaField(BaseField):
    """A base class for fields that directly map to JSON Schema validator.

    :param required:
        If the field is required, defaults to False.
    :type required: bool or :class:`Var`
    :param default:
        The default value for this field. May be a callable.
    :type default: any JSON-representable object, a callable or a :class:`Var`
    :param enum:
        A list of valid choices. May be a callable.
    :type enum: list, tuple, set or :class:`Var`
    :param title:
        A short explanation about the purpose of the data described by this field.
    :type title: string or :class:`Var`
    :param description:
        A detailed explanation about the purpose of the data described by this field.
    :type description: string or :class:`Var`
    """

    def __init__(self, id='', default=None, enum=None, title=None, description=None, **kwargs):
        self.id = id
        self.title = title
        self.description = description
        self._enum = enum
        self._default = default
        super(BaseSchemaField, self).__init__(**kwargs)

    def get_enum(self, role=DEFAULT_ROLE):
        enum = maybe_resolve(self._enum, role)
        if callable(enum):
            enum = enum()
        return enum

    def get_default(self, role=DEFAULT_ROLE):
        default = maybe_resolve(self._default, role)
        if callable(default):
            default = default()
        return default

    def _update_schema_with_common_fields(self, schema, id='', role=DEFAULT_ROLE):
        if id:
            schema['id'] = id
        title = maybe_resolve(self.title, role)
        if title is not None:
            schema['title'] = title
        description = maybe_resolve(self.description, role)
        if description is not None:
            schema['description'] = description
        enum = self.get_enum(role=role)
        if enum:
            schema['enum'] = list(enum)
        default = self.get_default(role=role)
        if default is not None:
            schema['default'] = default
        return schema


class BooleanField(BaseSchemaField):
    """A boolean field."""

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        schema = (OrderedDict if ordered else dict)(type='boolean')
        schema = self._update_schema_with_common_fields(schema, id=id, role=role)
        return {}, schema


class StringField(BaseSchemaField):
    """A string field.

    :param pattern:
        A regular expression (ECMA 262) that a string value must match.
    :type pattern: string or :class:`Var`
    :param format:
        A semantic format of the string (for example, "date-time", "email", or "uri").
    :type format: string or :class:`Var`
    :param min_length:
        A minimum length.
    :type min_length: int or :class:`Var`
    :param max_length:
        A maximum length.
    :type max_length: int or :class:`Var`
    """
    _FORMAT = None

    def __init__(self, pattern=None, format=None, min_length=None, max_length=None, **kwargs):
        self.pattern = pattern
        if self.pattern is not None:
            for value in maybe_resolve_all_roles(self.pattern):
                _validate_regex(value)
        self.format = format or self._FORMAT
        self.max_length = max_length
        self.min_length = min_length
        super(StringField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        schema = (OrderedDict if ordered else dict)(type='string')
        schema = self._update_schema_with_common_fields(schema, id=id, role=role)

        pattern = maybe_resolve(self.pattern, role)
        if pattern:
            schema['pattern'] = pattern
        min_length = maybe_resolve(self.min_length, role)
        if min_length is not None:
            schema['minLength'] = min_length
        max_length = maybe_resolve(self.max_length, role)
        if max_length is not None:
            schema['maxLength'] = max_length
        format = maybe_resolve(self.format, role)
        if format is not None:
            schema['format'] = format
        return {}, schema


class EmailField(StringField):
    """An email field."""
    _FORMAT = 'email'


class IPv4Type(StringField):
    """An IPv4 field."""
    _FORMAT = 'ipv4'


class DateTimeField(StringField):
    """An ISO 8601 formatted date-time field."""
    _FORMAT = 'date-time'


class UriField(StringField):
    """A URI field."""
    _FORMAT = 'uri'


class NumberField(BaseSchemaField):
    """A number field.

    :param multiple_of:
        A value must be a multiple of this factor.
    :type multiple_of: number or :class:`Var`
    :param minimum:
        A minimum allowed value.
    :type minimum: number or :class:`Var`
    :param exclusive_minimum:
        Whether a value is allowed to exactly equal the minimum.
    :type exclusive_minimum: bool or :class:`Var`
    :param maximum:
        A maximum allowed value.
    :type maximum: number or :class:`Var`
    :param exclusive_maximum:
        Whether a value is allowed to exactly equal the maximum.
    :type exclusive_maximum: bool or :class:`Var`
    """
    _NUMBER_TYPE = 'number'

    def __init__(self, multiple_of=None, minimum=None, maximum=None,
                 exclusive_minimum=False, exclusive_maximum=False, **kwargs):
        self.multiple_of = multiple_of
        self.minimum = minimum
        self.exclusive_minimum = exclusive_minimum
        self.maximum = maximum
        self.exclusive_maximum = exclusive_maximum
        super(NumberField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        schema = (OrderedDict if ordered else dict)(type=self._NUMBER_TYPE)
        schema = self._update_schema_with_common_fields(schema, id=id, role=role)
        multiple_of = maybe_resolve(self.multiple_of, role)
        if multiple_of is not None:
            schema['multipleOf'] = multiple_of
        minimum = maybe_resolve(self.minimum, role)
        if minimum is not None:
            schema['minimum'] = minimum
        exclusive_minimum = maybe_resolve(self.exclusive_minimum, role)
        if exclusive_minimum:
            schema['exclusiveMinumum'] = exclusive_minimum
        maximum = maybe_resolve(self.maximum, role)
        if maximum is not None:
            schema['maximum'] = maximum
        exclusive_maximum = maybe_resolve(self.exclusive_maximum, role)
        if exclusive_maximum:
            schema['exclusiveMaximum'] = exclusive_maximum
        return {}, schema


class IntField(NumberField):
    """An integer field."""
    _NUMBER_TYPE = 'integer'


class ArrayField(BaseSchemaField):
    """An array field.

    :param items:
        Either of the following:

        * :class:`BaseField` -- all items of the array must match the field schema;
        * a list or a tuple of :class:`BaseField` s -- all items of the array must be
          valid according to the field schema at the corresponding index (tuple typing).

    :param min_items:
        A minimum length of an array.
    :type min_items: int or :class:`Var`
    :param max_items:
        A maximum length of an array.
    :type max_items: int or :class:`Var`
    :param unique_items:
        Whether all the values in the array must be distinct.
    :type unique_items: bool or :class:`Var`
    :param additional_items:
        If the value of ``items`` is a list or a tuple, and the array length is larger than
        the number of fields in ``items``, then the additional items are described
        by the :class:`BaseField` passed using this argument.
    :type additional_items: bool or :class:`BaseField` or :class:`Var`
    """

    def __init__(self, items, min_items=None, max_items=None, unique_items=False,
                 additional_items=None, **kwargs):
        self.items = items
        self.min_items = min_items
        self.max_items = max_items
        self.unique_items = unique_items
        self.additional_items = additional_items
        super(ArrayField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        nested_definitions = {}
        schema = (OrderedDict if ordered else dict)(type='array')

        items, items_role = maybe_resolve_2(self.items, role)
        if items is not None:
            # TODO is it possible? an array without items?
            if isinstance(items, (list, tuple)):
                nested_schema = []
                for item in self.items:
                    item, items_role = maybe_resolve_2(item, role)
                    item_definitions, item_schema = item.get_definitions_and_schema(
                        role=items_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
                    nested_definitions.update(item_definitions)
                    nested_schema.append(item_schema)
            else:
                nested_definitions, nested_schema = items.get_definitions_and_schema(
                    role=items_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
            schema = self._update_schema_with_common_fields(schema, id=id, role=role)
            schema['items'] = nested_schema

        additional_items, additional_items_role = maybe_resolve_2(self.additional_items, role)
        if additional_items is not None:
            if isinstance(additional_items, bool):
                schema['additionalItems'] = additional_items
            else:
                items_definitions, items_schema = additional_items.get_definitions_and_schema(
                    role=additional_items_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
                schema['additionalItems'] = items_schema
                nested_definitions.update(items_definitions)

        min_items = maybe_resolve(self.min_items, role)
        if min_items is not None:
            schema['minItems'] = min_items
        max_items = maybe_resolve(self.max_items, role)
        if max_items is not None:
            schema['maxItems'] = max_items
        unique_items = maybe_resolve(self.unique_items, role)
        if unique_items:
            schema['uniqueItems'] = True
        return nested_definitions, schema

    def iter_fields(self, role=DEFAULT_ROLE):
        items, items_role = maybe_resolve_2(self.items, role)
        if items is not None:
            # TODO is it possible? an array without items?
            if isinstance(items, (list, tuple)):
                for item in items:
                    item = maybe_resolve(item, items_role)
                    yield item
            else:
                yield items
        additional_items = maybe_resolve(self.additional_items, role)
        if isinstance(additional_items, BaseField):
            yield additional_items


class DictField(BaseSchemaField):
    """A dictionary field.

    :param properties:
        A dictionary containing fields.
    :type properties: dict from str to :class:`BaseField` or :class:`Var`
    :param pattern_properties:
        A dictionary whose keys are regular expressions (ECMA 262).
        Properties match against these regular expressions, and for any that match,
        the property is described by the corresponding field schema.
    :type pattern_properties: dict from str to :class:`BaseField` or :class:`Var`
    :param additional_properties:
        Describes properties that are not described by the ``properties`` or ``pattern_properties``.
    :type additional_properties: bool or :class:`BaseField` or :class:`Var`
    :param min_properties:
        A minimum number of properties.
    :type min_properties: int or :class:`Var`
    :param max_properties:
        A maximum number of properties
    :type max_properties: int or :class:`Var`
    """

    def __init__(self, properties=None, pattern_properties=None, additional_properties=None,
                 min_properties=None, max_properties=None, **kwargs):
        self.properties = properties
        self.pattern_properties = pattern_properties
        self.additional_properties = additional_properties
        self.min_properties = min_properties
        self.max_properties = max_properties
        super(DictField, self).__init__(**kwargs)

    def _process_properties(self, properties, scope, ordered=False, ref_documents=None, role=DEFAULT_ROLE):
        nested_definitions = {}
        schema = OrderedDict() if ordered else {}
        required = []
        for prop, field in iteritems(properties):
            field, field_role = maybe_resolve_2(field, role)
            if field is None:
                continue
            field_definitions, field_schema = field.get_definitions_and_schema(
                role=field_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
            if maybe_resolve(field.required, field_role):
                required.append(prop)
            schema[prop] = field_schema
            nested_definitions.update(field_definitions)
        return nested_definitions, required, schema

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        nested_definitions = {}
        schema = (OrderedDict if ordered else dict)(type='object')
        id, scope = scope.alter(self.id)
        schema = self._update_schema_with_common_fields(schema, id=id, role=role)

        properties, properties_role = maybe_resolve_2(self.properties, role)
        if properties is not None:
            properties_definitions, properties_required, properties_schema = self._process_properties(
                properties, scope, ordered=ordered, ref_documents=ref_documents, role=properties_role)
            schema['properties'] = properties_schema
            if properties_required:
                schema['required'] = properties_required
            nested_definitions.update(properties_definitions)

        pattern_properties, pattern_properties_role = maybe_resolve_2(self.pattern_properties, role)
        if pattern_properties is not None:
            for key in iterkeys(pattern_properties):
                _validate_regex(key)
            properties_definitions, _, properties_schema = self._process_properties(
                pattern_properties, scope, ordered=ordered, ref_documents=ref_documents,
                role=pattern_properties_role)
            schema['patternProperties'] = properties_schema
            nested_definitions.update(properties_definitions)

        additional_properties, additional_properties_role = maybe_resolve_2(self.additional_properties, role)
        if additional_properties is not None:
            if isinstance(additional_properties, bool):
                schema['additionalProperties'] = additional_properties
            else:
                properties_definitions, properties_schema = additional_properties.get_definitions_and_schema(
                    role=additional_properties_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
                schema['additionalProperties'] = properties_schema
                nested_definitions.update(properties_definitions)

        min_properties = maybe_resolve(self.min_properties, role)
        if min_properties is not None:
            schema['minProperties'] = min_properties
        max_properties = maybe_resolve(self.max_properties, role)
        if max_properties is not None:
            schema['maxProperties'] = max_properties

        return nested_definitions, schema

    def iter_fields(self, role=DEFAULT_ROLE):
        properties, properties_role = maybe_resolve_2(self.properties, role)
        if properties is not None:
            for field in itervalues(properties):
                field = maybe_resolve(field, properties_role)
                if field is not None:
                    yield field
        pattern_properties, pattern_properties_role = maybe_resolve_2(self.pattern_properties, role)
        if pattern_properties is not None:
            for field in itervalues(pattern_properties):
                field = maybe_resolve(field, pattern_properties_role)
                if field is not None:
                    yield field
        additional_properties = maybe_resolve(self.additional_properties, role)
        if additional_properties is not None and isinstance(additional_properties, BaseField):
            yield additional_properties


class BaseOfField(BaseSchemaField):
    _KEYWORD = None

    def __init__(self, fields, **kwargs):
        self.fields = fields
        super(BaseOfField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        nested_definitions = {}
        one_of = []
        fields, fields_role = maybe_resolve_2(self.fields, role)
        if fields is not None:
            for field in fields:
                field, field_role = maybe_resolve_2(field, fields_role)
                if field is None:
                    continue
                field_definitions, field_schema = field.get_definitions_and_schema(
                    role=field_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
                nested_definitions.update(field_definitions)
                one_of.append(field_schema)
        schema = OrderedDict() if ordered else {}
        schema[self._KEYWORD] = one_of
        schema = self._update_schema_with_common_fields(schema, id=id)
        return nested_definitions, schema

    def iter_fields(self, role=DEFAULT_ROLE):
        fields, fields_role = maybe_resolve_2(self.fields, role)
        for field in fields:
            field = maybe_resolve(field, fields_role)
            yield field


class OneOfField(BaseOfField):
    """
    :param fields: a list of fields, exactly one of which describes the data
    :type fields: list whose elements are :class:`BaseField` s or :class:`Var` s
    """
    _KEYWORD = 'oneOf'


class AnyOfField(BaseOfField):
    """
    :param fields: a list of fields, at least one of which describes the data
    :type fields: list whose elements are :class:`BaseField` s or :class:`Var` s
    """
    _KEYWORD = 'anyOf'


class AllOfField(BaseOfField):
    """
    :param fields: a list of fields, all of which describe the data
    :type fields: list whose elements are :class:`BaseField` s or :class:`Var` s
    """
    _KEYWORD = 'allOf'


class NotField(BaseSchemaField):
    """
    :param field: a field to negate
    :type field: :class:`BaseField`
    """

    def __init__(self, field, **kwargs):
        self.field = field
        super(NotField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        id, scope = scope.alter(self.id)
        field, field_role = maybe_resolve_2(self.field, role)
        if field is not None:
            field_definitions, field_schema = field.get_definitions_and_schema(
                role=field_role, scope=scope, ordered=ordered, ref_documents=ref_documents)
        else:
            field_definitions = {}
            field_schema = {}
        schema = OrderedDict() if ordered else {}
        schema['not'] = field_schema
        schema = self._update_schema_with_common_fields(schema, id=id, role=role)
        return field_definitions, schema


class DocumentField(BaseField):
    """A reference to a nested document.

    :param document_cls:
        A string (dot-separated path to document class, i.e. 'app.resources.User'),
        :data:`RECURSIVE_REFERENCE_CONSTANT` or a :class:`Document`
    :param as_ref:
        If true, ``document_cls``'s schema is placed into the definitions section, and
        the field schema is just a reference to it: ``{"$ref": "#/definitions/..."}``.
        Makes a resulting schema more readable.
    """

    def __init__(self, document_cls, as_ref=False, **kwargs):
        """
        :type document_cls: basestring or BaseField
        """
        self._document_cls = document_cls
        self.owner_cls = None
        self.as_ref = as_ref
        super(DocumentField, self).__init__(**kwargs)

    def iter_fields(self, role=DEFAULT_ROLE):
        document_cls = self.get_document_cls(role=role)
        return document_cls.iter_fields(role=role)

    def walk(self, role=DEFAULT_ROLE, through_document_fields=False, visited_documents=frozenset()):
        yield self
        if through_document_fields:
            document_cls = self.get_document_cls(role=role)
            if document_cls not in visited_documents:
                visited_documents = visited_documents | set([document_cls])
                for field in super(DocumentField, self).walk(
                        role=role,
                        through_document_fields=through_document_fields,
                        visited_documents=visited_documents):
                    if field != self:  # TODO feels like a hack
                        yield field

    def get_definitions_and_schema(self, role=DEFAULT_ROLE, scope=ResolutionScope(), ordered=False, ref_documents=None):
        document_cls = self.get_document_cls(role=role)
        definition_id = document_cls.get_definition_id()
        if ref_documents and document_cls in ref_documents:
            return {}, scope.create_ref(definition_id)
        else:
            document_definitions, document_schema = document_cls.get_definitions_and_schema(
                role=role, scope=scope, ordered=ordered, ref_documents=ref_documents)
            if self.as_ref:
                document_definitions[definition_id] = document_schema
                return document_definitions, scope.create_ref(definition_id)
            else:
                return document_definitions, document_schema

    def set_owner(self, owner_cls):
        self.owner_cls = owner_cls

    def get_document_cls(self, role=DEFAULT_ROLE):
        document_cls = maybe_resolve(self._document_cls, role)
        if isinstance(document_cls, string_types):
            if document_cls == RECURSIVE_REFERENCE_CONSTANT:
                if self.owner_cls is None:
                    raise ValueError('owner_cls is not set')
                return self.owner_cls
            else:
                try:
                    return registry.get_document(document_cls)
                except KeyError:
                    if self.owner_cls is None:
                        raise ValueError('owner_cls is not set')
                    return registry.get_document(document_cls, module=self.owner_cls.__module__)
        else:
            return document_cls
