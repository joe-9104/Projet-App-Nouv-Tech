# Generated for VIS-01 and VIS-02

import uuid
import django.db.models.deletion
from django.db import migrations, models


def backfill_reference_ids(apps, schema_editor):
    DocumentFigure = apps.get_model('documents', 'DocumentFigure')
    for figure in DocumentFigure.objects.select_related('extracted_document__document').all():
        document = figure.extracted_document.document
        figure.reference_id = f"img_{document.id.hex}_{figure.page_index}_{figure.source_block_id}"
        figure.save(update_fields=['reference_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_extracteddocument_documentfigure'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentfigure',
            name='reference_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='documentfigure',
            name='dimensions',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='documentfigure',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='documentfigure',
            name='source_block_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_reference_ids, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='documentfigure',
            index=models.Index(fields=['extracted_document', 'page_index'], name='figure_extraction_page_idx'),
        ),
        migrations.AddConstraint(
            model_name='documentfigure',
            constraint=models.UniqueConstraint(fields=('extracted_document', 'reference_id'), name='unique_figure_reference_per_extraction'),
        ),
        migrations.CreateModel(
            name='FigurePassageAssociation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('passage_block_id', models.CharField(max_length=255)),
                ('page_index', models.IntegerField()),
                ('confidence', models.CharField(choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], max_length=10)),
                ('provenance', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('extracted_document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='figure_associations', to='documents.extracteddocument')),
                ('figure', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='passage_associations', to='documents.documentfigure')),
            ],
            options={'indexes': [models.Index(fields=['extracted_document', 'passage_block_id'], name='association_passage_idx')]},
        ),
        migrations.AddConstraint(
            model_name='figurepassageassociation',
            constraint=models.UniqueConstraint(fields=('figure', 'passage_block_id'), name='unique_figure_passage'),
        ),
    ]
