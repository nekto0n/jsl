# coding: utf-8
import pytest

from jsl import (Document, BaseSchemaField, StringField, ArrayField, DocumentField, IntField,
                 DateTimeField, NumberField, DictField, NotField,
                 AllOfField, AnyOfField, OneOfField)
from jsl.roles import Var, Not


def test_var():
    value_1 = object()
    value_2 = object()
    value_3 = object()
    var = Var([
        ('role_1', value_1),
        ('role_2', value_2),
        (Not('role_3'), value_3),
    ])
    assert var.resolve('role_1') == value_1
    assert var.resolve('role_2') == value_2
    assert var.resolve('default') == value_3

    var = Var([
        (Not('role_3'), value_3),
        ('role_1', value_1),
        ('role_2', value_2),
    ])
    assert var.resolve('role_1') == value_3
    assert var.resolve('role_2') == value_3
    assert var.resolve('default') == value_3
    assert var.resolve('role_3') is None


def test_base_field():
    _ = lambda value: Var({'role_1': value})
    field = BaseSchemaField(default=_(lambda: 1), enum=_(lambda: [1, 2, 3]), title=_('Title'),
                            description=_('Description'))
    schema = {}
    schema = field._update_schema_with_common_fields(schema)
    assert schema == {}

    schema = field._update_schema_with_common_fields(schema, role='role_1')
    assert schema == {
        'title': 'Title',
        'description': 'Description',
        'enum': [1, 2, 3],
        'default': 1,
    }


def test_string_field():
    _ = lambda value: Var({'role_1': value})
    field = StringField(format=_('date-time'), min_length=_(1), max_length=_(2))
    assert field.get_schema() == {
        'type': 'string'
    }
    assert field.get_schema(role='role_1') == {
        'type': 'string',
        'format': 'date-time',
        'minLength': 1,
        'maxLength': 2,
    }

    with pytest.raises(ValueError) as e:
        StringField(pattern=_('('))
    assert str(e.value) == 'Invalid regular expression: unbalanced parenthesis'


def test_array_field():
    s_f = StringField()
    n_f = NumberField()
    field = ArrayField(Var({
        'role_1': s_f,
        'role_2': n_f,
    }))
    schema = field.get_schema(role='role_1')
    assert schema['items'] == s_f.get_schema()

    schema = field.get_schema(role='role_2')
    assert schema['items'] == n_f.get_schema()

    schema = field.get_schema()
    assert 'items' not in schema

    _ = lambda value: Var({'role_1': value})
    field = ArrayField(s_f, min_items=_(1), max_items=_(2), unique_items=_(True), additional_items=_(True))
    assert field.get_schema() == {
        'type': 'array',
        'items': s_f.get_schema(),
    }
    assert field.get_schema(role='role_1') == {
        'type': 'array',
        'items': s_f.get_schema(),
        'minItems': 1,
        'maxItems': 2,
        'uniqueItems': True,
        'additionalItems': True,
    }


def test_dict_field():
    s_f = StringField()
    _ = lambda value: Var({'role_1': value})
    field = DictField(properties=Var(
        role_1={'name': Var(role_1=s_f)},
        role_2={'name': Var(role_2=s_f)},
        roles_to_pass_down=['role_1']
    ), pattern_properties=Var(
        role_1={'.*': Var(role_1=s_f)},
        role_2={'.*': Var(role_2=s_f)},
        roles_to_pass_down=['role_1']
    ), additional_properties=_(s_f), min_properties=_(1), max_properties=_(2))
    assert field.get_schema() == {
        'type': 'object'
    }
    assert field.get_schema(role='role_1') == {
        'type': 'object',
        'properties': {
            'name': s_f.get_schema(),
        },
        'patternProperties': {
            '.*': s_f.get_schema(),
        },
        'additionalProperties': s_f.get_schema(),
        'minProperties': 1,
        'maxProperties': 2,
    }
    assert field.get_schema(role='role_2') == {
        'type': 'object',
        'properties': {},
        'patternProperties': {},
    }


@pytest.mark.parametrize(('keyword', 'field_cls'),
                         [('oneOf', OneOfField), ('anyOf', AnyOfField), ('allOf', AllOfField)])
def test_keyword_of_fields(keyword, field_cls):
    s_f = StringField()
    n_f = NumberField()
    i_f = IntField()
    field = field_cls([n_f, Var(role_1=s_f), Var(role_2=i_f)])
    assert field.get_schema() == {
        keyword: [n_f.get_schema()]
    }
    assert field.get_schema(role='role_1') == {
        keyword: [n_f.get_schema(), s_f.get_schema()]
    }
    assert field.get_schema(role='role_2') == {
        keyword: [n_f.get_schema(), i_f.get_schema()]
    }

    field = field_cls(Var(
        role_1=[n_f, Var(role_1=s_f), Var(role_2=i_f)],
        role_2=[Var(role_2=i_f)],
        roles_to_pass_down=['role_1']
    ))
    assert field.get_schema() == {keyword: []}
    assert field.get_schema(role='role_1') == {
        keyword: [n_f.get_schema(), s_f.get_schema()]
    }
    assert field.get_schema(role='role_2') == {keyword: []}


def test_not_field():
    s_f = StringField()
    field = NotField(Var(role_1=s_f))
    assert field.get_schema() == {'not': {}}
    assert field.get_schema(role='role_1') == {'not': s_f.get_schema()}


def test_document_field():
    class B(Document):
        name = Var(
            response=StringField(required=True),
            request=StringField()
        )

    class A(Document):
        id = Var(response=StringField(required=True))
        b = DocumentField(B)

    field = DocumentField(A)

    # test iter_fields method
    assert list(field.iter_fields()) == [A.b]
    assert (sorted(list(field.iter_fields(role='response')), key=id) ==
            sorted([A.b, A.id.values['response']], key=id))

    # test walk method
    w = list(field.walk())
    assert w == [field]

    w = list(field.walk(through_document_fields=True))
    assert w == [field, A.b]

    w = list(field.walk(through_document_fields=True, role='response'))
    assert (sorted(w, key=id) ==
            sorted([field, A.b, A.id.values['response'], B.name.values['response']], key=id))

    w = list(field.walk(through_document_fields=True, role='request'))
    assert sorted(w, key=id) == sorted([field, A.b, B.name.values['request']], key=id)

    class X(Document):
        pass
    class Y(Document):
        pass
    field = DocumentField(Var({
        'role_1': X,
        'role_2': Y
    }))
    assert field.get_document_cls() is None
    assert field.get_document_cls(role='role_1') == X
    assert field.get_document_cls(role='role_2') == Y


def test_basics():
    class User(Document):
        id = Var({
            'response': IntField(required=True)
        })
        login = StringField(required=True)

    class Task(Document):
        class Options(object):
            title = 'Task'
            description = 'A task.'
            definition_id = 'task'

        id = IntField(required=Var({'response': True}))
        name = StringField(required=True, min_length=5)
        type = StringField(required=True, enum=['TYPE_1', 'TYPE_2'])
        created_at = DateTimeField(required=True)
        author = Var({'response': DocumentField(User)}, roles_to_pass_down=['response'])

    expected_schema = {
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'additionalProperties': False,
        'description': 'A task.',
        'properties': {
            'created_at': {'format': 'date-time', 'type': 'string'},
            'id': {'type': 'integer'},
            'name': {'minLength': 5, 'type': 'string'},
            'type': {'enum': ['TYPE_1', 'TYPE_2'], 'type': 'string'}
        },
        'required': ['created_at', 'type', 'name'],
        'title': 'Task',
        'type': 'object'
    }
    schema = Task.get_schema()
    expected_schema['required'].sort()
    schema['required'].sort()
    assert schema == expected_schema

    expected_schema = {
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'title': 'Task',
        'description': 'A task.',
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'created_at': {'format': 'date-time', 'type': 'string'},
            'id': {'type': 'integer'},
            'name': {'minLength': 5, 'type': 'string'},
            'type': {'enum': ['TYPE_1', 'TYPE_2'], 'type': 'string'},
            'author': {
                'additionalProperties': False,
                'properties': {
                    'id': {'type': 'integer'},
                    'login': {'type': 'string'}
                },
                'required': ['id', 'login'],
                'type': 'object'
            },
        },
        'required': ['created_at', 'type', 'name', 'id'],
    }
    schema = Task.get_schema(role='response')
    expected_schema['required'].sort()
    expected_schema['properties']['author']['required'].sort()
    schema['required'].sort()
    schema['properties']['author']['required'].sort()
    assert schema == expected_schema
