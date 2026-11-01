from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='CompletedCourse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('course_name', models.CharField(max_length=120, verbose_name='課程名稱')),
                ('credits', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)], verbose_name='學分數')),
                ('category', models.CharField(choices=[('REQUIRED', '必修'), ('ELECTIVE', '選修')], max_length=10, verbose_name='課程類別')),
                ('semester', models.CharField(help_text='例如：114-1', max_length=30, verbose_name='修課學期')),
                ('grade', models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='成績（選填）')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='建立時間')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='completed_courses', to=settings.AUTH_USER_MODEL, verbose_name='學生')),
            ],
            options={'verbose_name': '已完成課程', 'verbose_name_plural': '已完成課程紀錄', 'ordering': ['-semester', 'course_name']},
        ),
    ]
