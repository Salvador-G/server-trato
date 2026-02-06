from rest_framework import serializers
from .models import Formulario, FormularioEnvio
from django.db import models
from core.models import BrandUser
from django.utils.text import slugify


class FormularioCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True)

    class Meta:
        model = Formulario
        fields = (
            "name",          # viene del builder
            "schema",
            "descripcion",
            "is_public",
        )

    def validate_schema(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Schema debe ser una lista de campos"
            )

        for field in value:
            if "id" not in field or "type" not in field:
                raise serializers.ValidationError(
                    "Cada campo debe tener id y type"
                )

        return value

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        # Resolver marca activa del usuario
        try:
            brand_user = (
                BrandUser.objects
                .select_related("brand")
                .get(user=user, is_active=True)
            )
        except BrandUser.DoesNotExist:
            raise serializers.ValidationError(
                "El usuario no pertenece a ninguna marca activa"
            )

        brand = brand_user.brand

        name = validated_data.pop("name")
        schema = validated_data.pop("schema")

        form_key = slugify(name)

        last_version = (
            Formulario.objects
            .filter(brand=brand, form_key=form_key)
            .aggregate(models.Max("version"))
            .get("version__max") or 0
        )

        return Formulario.objects.create(
            brand=brand,
            form_key=form_key,
            schema={"schema": schema},  # formato consistente
            version=last_version + 1,
            created_by=user,
            **validated_data,
        )

class FormularioListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Formulario
        fields = (
            "id",
            "form_key",
            "version",
            "descripcion",
            "is_public",
            "is_active",
            "created_at",
        )

class FormularioPublicSerializer(serializers.ModelSerializer):
    schema = serializers.SerializerMethodField()
    meta = serializers.SerializerMethodField()

    class Meta:
        model = Formulario
        fields = (
            "form_key",
            "version",
            "schema",
            "meta",
        )

    def get_schema(self, obj):
        # Extraer solo el array para el widget
        return obj.schema.get("schema", [])
    
    def get_meta(self, obj):
        return {
            "brand": obj.brand.slug,
            "form_key": obj.form_key,
        }


class FormularioEnvioCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormularioEnvio
        fields = (
            "formulario",
            "payload",
            "source",
            "cliente",
        )

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Payload inválido")
        return value
