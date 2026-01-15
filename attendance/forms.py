from django import forms
from .models import FeatureSuggestion


class FeatureSuggestionForm(forms.ModelForm):
    class Meta:
        model = FeatureSuggestion
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
        labels = {
            'title': 'Title',
            'description': 'Description',
        }
