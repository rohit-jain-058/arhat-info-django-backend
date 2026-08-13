# apps/resumes/serializers.py
from rest_framework import serializers
from .models import Resume


class ResumeSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model  = Resume
        fields = [
            'id', 'name', 'file_url', 'raw_text',
            'skills', 'experience', 'achievements',
            'years_experience', 'career_goal', 'summary',
            'ai_processed', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'file_url', 'ai_processed', 'created_at', 'updated_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class ResumeUploadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    file = serializers.FileField()

    def validate_file(self, value):
        # Max 5MB
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('File size must be under 5MB.')
        # PDF or DOCX only
        allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if value.content_type not in allowed:
            raise serializers.ValidationError('Only PDF and DOCX files are supported.')
        return value


class ResumeEditSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Resume
        fields = [
            'name', 'skills', 'experience',
            'achievements', 'years_experience',
            'career_goal', 'summary',
        ]
