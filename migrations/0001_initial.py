
from south.db import db
from django.db import models
from www.widgets.models import *

class Migration:
    
    def forwards(self, orm):
        
        # Adding model 'WikiHome'
        db.create_table('widgets_wikihome', (
            ('id', orm['widgets.WikiHome:id']),
            ('slug', orm['widgets.WikiHome:slug']),
        ))
        db.send_create_signal('widgets', ['WikiHome'])
        
        # Adding model 'WikiPage'
        db.create_table('widgets_wikipage', (
            ('id', orm['widgets.WikiPage:id']),
            ('wiki', orm['widgets.WikiPage:wiki']),
            ('slug', orm['widgets.WikiPage:slug']),
            ('created_by', orm['widgets.WikiPage:created_by']),
            ('created_at', orm['widgets.WikiPage:created_at']),
            ('modified_on', orm['widgets.WikiPage:modified_on']),
            ('head', orm['widgets.WikiPage:head']),
        ))
        db.send_create_signal('widgets', ['WikiPage'])
        
        # Adding model 'WidgetState'
        db.create_table('widgets_widgetstate', (
            ('id', orm['widgets.WidgetState:id']),
            ('widget', orm['widgets.WidgetState:widget']),
            ('previous', orm['widgets.WidgetState:previous']),
        ))
        db.send_create_signal('widgets', ['WidgetState'])
        
        # Creating unique_together for [wiki, slug] on WikiPage.
        db.create_unique('widgets_wikipage', ['wiki_id', 'slug'])
        
    
    
    def backwards(self, orm):
        
        # Deleting unique_together for [wiki, slug] on WikiPage.
        db.delete_unique('widgets_wikipage', ['wiki_id', 'slug'])
        
        # Deleting model 'WikiHome'
        db.delete_table('widgets_wikihome')
        
        # Deleting model 'WikiPage'
        db.delete_table('widgets_wikipage')
        
        # Deleting model 'WidgetState'
        db.delete_table('widgets_widgetstate')
        
    
    
    models = {
        'auth.group': {
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'unique_together': "(('content_type', 'codename'),)"},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True', 'blank': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'blank': 'True'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'blank': 'True'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'unique_together': "(('app_label', 'model'),)", 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'widgets.widgetstate': {
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'previous': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['widgets.WidgetState']", 'null': 'True', 'blank': 'True'}),
            'widget': ('PickleField', [], {})
        },
        'widgets.wikihome': {
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '400', 'db_index': 'True'})
        },
        'widgets.wikipage': {
            'Meta': {'unique_together': "(('wiki', 'slug'),)"},
            'created_at': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'created_by': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'null': 'True'}),
            'head': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['widgets.WidgetState']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'modified_on': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '400', 'db_index': 'True'}),
            'wiki': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['widgets.WikiHome']"})
        }
    }
    
    complete_apps = ['widgets']
