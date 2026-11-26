import django.db.models.deletion
from django.db import migrations, models
import pgvector.django.vector


def enable_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')


class Migration(migrations.Migration):
    dependencies = [('documents', '0003_visual_assets_associations')]

    operations = [
        migrations.RunPython(enable_pgvector, migrations.RunPython.noop),
        migrations.CreateModel(
            name='DocumentChunk',
            fields=[
                ('id', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('page_start', models.IntegerField()),
                ('page_end', models.IntegerField()),
                ('section_title', models.CharField(blank=True, max_length=512, null=True)),
                ('block_ids', models.JSONField(blank=True, default=list)),
                ('hierarchy', models.JSONField(blank=True, default=list)),
                ('figure_refs', models.JSONField(blank=True, default=list)),
                ('embedding', pgvector.django.vector.VectorField(dimensions=384)),
                ('embedding_model', models.CharField(max_length=255)),
                ('generation', models.CharField(max_length=64)),
                ('indexed_at', models.DateTimeField(auto_now=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='documents.document')),
                ('extracted_document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='documents.extracteddocument')),
            ],
        ),
        migrations.AddIndex(model_name='documentchunk', index=models.Index(fields=['document', 'generation'], name='chunk_document_generation_idx')),
        migrations.AddIndex(model_name='documentchunk', index=models.Index(fields=['document', 'page_start', 'page_end'], name='chunk_document_pages_idx')),
    ]
