from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CrashReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fingerprint', models.CharField(db_index=True, max_length=32)),
                ('exception', models.CharField(max_length=200)),
                ('stack', models.TextField()),
                ('thread', models.CharField(blank=True, default='', max_length=20)),
                ('app_version', models.CharField(blank=True, default='', max_length=40)),
                ('android', models.CharField(blank=True, default='', max_length=40)),
                ('device', models.CharField(blank=True, default='', max_length=120)),
                ('crashed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
