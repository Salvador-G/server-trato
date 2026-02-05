from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

# Import necessary modules for public access
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny

from .models import Formulario
from .serializers import (FormularioCreateSerializer, 
                            FormularioListSerializer, 
                            FormularioPublicSerializer, 
                            FormularioEnvioCreateSerializer)

# Create your views here.
class FormularioCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FormularioCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        form = serializer.save()

        return Response(
            FormularioListSerializer(form).data,
            status=status.HTTP_201_CREATED,
        )
        
class FormularioListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        forms = Formulario.objects.filter(
            created_by=request.user
        ).order_by("-created_at")

        serializer = FormularioListSerializer(forms, many=True)
        return Response(serializer.data)

class FormularioPublicAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, brand_slug, form_key):
        form = get_object_or_404(
            Formulario,
            brand__slug=brand_slug,
            form_key=form_key,
            is_public=True,
            is_active=True,
        )

        serializer = FormularioPublicSerializer(form)
        return Response(serializer.data)
    
class FormularioSubmitAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, brand_slug, form_key):
        form = get_object_or_404(
            Formulario,
            brand__slug=brand_slug,
            form_key=form_key,
            is_public=True,
            is_active=True,
        )

        serializer = FormularioEnvioCreateSerializer(
            data={
                "formulario": form.id,
                "payload": request.data,
                "source": "widget",
            }
        )

        serializer.is_valid(raise_exception=True)
        envio = serializer.save()

        return Response(
            {"submission_id": str(envio.submission_id)},
            status=status.HTTP_201_CREATED,
        )