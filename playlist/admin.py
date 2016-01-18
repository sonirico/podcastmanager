from django.contrib import admin
from playlist.models import *


class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'uploaded', 'expiration', 'promo_duration', 'tweet', 'category', 'is_active', 'thumbnail')
    date_hierarchy = 'uploaded'

    def is_active(self, instance):
        return instance.is_active()
    is_active.boolean = True

    def promo_duration(self, instance):
        m, s = divmod(instance.duration, 60)
        h, m = divmod(m, 60)
        return "%d:%02d:%02d" % (h, m, s)
    promo_duration.short_description = u'Duration'


class PromoCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'interval', 'expire', 'days_to_expiration')

    def interval(self, instance):
        m, s = divmod(instance.time_interval, 60)
        h, m = divmod(m, 60)
        return "%d:%02d:%02d" % (h, m, s)
    interval.short_description = u'Time lapse to be displayed at the playlist'


class PodcastCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'max_times_played', 'duration', 'days_to_expiration', 'days_to_inactive', 'podcast_count')

    def podcast_count(self, instance):
        return instance.podcast_set.count()

    def duration(self, instance):
        m, s = divmod(instance.max_duration, 60)
        h, m = divmod(m, 60)
        return "%d:%02d:%02d" % (h, m, s)
    duration.short_description = u'Max duration'


class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'podcast', 'published', 'downloaded', 'custom_duration', 'times_played', 'active', 'thumbnail')
    search_fields = ('title',)
    ordering = ['-downloaded']
    date_hierarchy = 'downloaded'

    def custom_duration(self, instance):
        m, s = divmod(instance.duration, 60)
        h, m = divmod(m, 60)
        return "%d:%02d:%02d" % (h, m, s)
    custom_duration.short_description = u'Duration'

    def active(self, instance):
        return instance.is_active()
    active.boolean = True


class EpisodeInline(admin.StackedInline):
    model = Episode
    fields = ['title', 'times_played', 'filename', 'cover']
    ordering = ['-published']

    def is_active(self, instance):
        return instance.is_active()
    is_active.boolean = True
    is_active.short_description = u'Active'


class PodcastAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'description', 'feed', 'website', 'active')
    list_filter = ('active',)
    search_fields = ('name', 'website',)
    inlines = [EpisodeInline,]


class PlaylistHistoryAdmin(admin.ModelAdmin):
    list_display = ('started', 'finished', 'podcast', 'audio', 'total_unique_listeners_count')
    ordering = ['-started']

    def podcast(self, instance):
        audio_type = instance.audio.get_type()
        if audio_type == u'episode':
            return instance.audio.podcast


admin.site.register(PodcastCategory, PodcastCategoryAdmin)
admin.site.register(PromoCategory, PromoCategoryAdmin)
admin.site.register(Podcast, PodcastAdmin)
admin.site.register(Episode, EpisodeAdmin)
#admin.site.register(Episode)
admin.site.register(Promotion, PromotionAdmin)
admin.site.register(PlaylistHistory, PlaylistHistoryAdmin)
