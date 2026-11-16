-- Instagram stories (race week fact cards, one image per story) are tracked like posts.
alter table public.ig_posts drop constraint if exists ig_posts_kind_check;
alter table public.ig_posts add constraint ig_posts_kind_check check (kind in ('reel', 'carousel', 'story'));
