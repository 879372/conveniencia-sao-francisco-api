from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('compras', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemnotacompra',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='notacompra',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
    ]
