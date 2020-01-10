from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import json
import jsonschema


class FieldReference:
    def __init__(self, source):
        self.source = source.split('.')

    def __call__(self, instance, *args, **kwargs):
        obj = instance
        for attr in self.source:
            obj = getattr(obj, attr)
        return obj


class JSONSchemaField(JSONField):
    """
    Usage examples:
        class ModelA(models.Model):
            json_schema_field = JSONSchemaField()

        class ModelB(models.Model):
            # passing a string with the model field attribute name that holds the JSON Schema
            json_schema_field = JSONSchemaField()
            json_field_z = JSONSchemaField('json_schema_field')

            # passing a dotted string with the model field attribute name that holds the JSON Schema even in a
            # related model
            model_a = models.ForeignKey(ModelA)
            json_field_y = JSONSchemaField('model_a.json_schema_field')

            # passing a mixed python object that represents the JSON Schema (that's how JSON Schema is actually treated
            # internally in Python)
            json_field_w = JSONSchemaField({
                '$schema': 'http://json-schema.org/draft-07/schema#',
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'a_not_required_field': {'type': 'string'},
                },
                'required': ['id', 'a_not_required_field']
            })

            # passing a string representing a JSON Schema
            json_field_x_a = JSONSchemaField('''{
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "a_not_required_field": {"type": "string"},
                },
                "required": ["id", "a_not_required_field"]
            }''')

            # passing a callabe that receives a model instance and returns the JSON Schema
            json_field_x_b = JSONSchemaField(lambda x: {
                '$schema': 'http://json-schema.org/draft-07/schema#',
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'a_not_required_field': {'type': 'string'},
                },
                'required': ['id', 'a_not_required_field']
            })
    """
    description = _('A JSON object with JSON Schema validation support.')
    default_error_messages = {
        'invalid': _("Value must be valid JSON."),
        'invalid_schema_definition': _("Value must be valid JSON Schema."),
        'invalid_data': _("Value must respect schema definition."),
    }

    def __init__(self, schema=None, format_checker=None, *args, **kwargs):
        """
        schema: should be 'None', a mixed 'dict' JSON serializable or a 'callable' with the mandatory 'model_instance'
            argument that will receive the bounded model's instance
        format_checker: should be an "jsonschema.IValidator' (e.g. jsonschema.Draft6Validator,
            jsonschema.Draft7Validator, etc.). In case of 'None' it will try to infer from the value of schema's
            '$schema' key. In last case with there isn't a '$schema' key or it's invalid it will defaults to the latest
            draft version format checker available on jsonschema
        """
        super().__init__(*args, **kwargs)

        self._schema_kwarg = schema
        if schema is None:
            schema = {}
        elif isinstance(schema, str):
            # Try to load a json from the string or use it as dotted field path reference
            options = {'cls': self.encoder} if self.encoder else {}
            try:
                schema = json.loads(schema, **options)
            except json.decoder.JSONDecodeError:
                schema = FieldReference(source=schema)

        self.format_checker = format_checker
        self._schema = schema

    def get_schema(self, model_instance):
        schema = self._schema
        if callable(schema):
            schema = schema(model_instance)
        return schema

    def validate_against_schema(self, value, model_instance):
        """Validates the value against the defined JSON Schema"""
        schema = self.get_schema(model_instance)
        try:
            jsonschema.validate(value, schema, cls=self.format_checker)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(e.message, code='invalid_data')
        except jsonschema.exceptions.SchemaError as e:
            raise ValidationError(e.message, code='invalid_schema_definition')

    def validate(self, value, model_instance):  # pragma: no cover
        super().validate(value, model_instance)
        self.validate_against_schema(value, model_instance)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["schema"] = self._schema_kwarg
        kwargs["format_checker"] = self.format_checker
        return name, path, args, kwargs
