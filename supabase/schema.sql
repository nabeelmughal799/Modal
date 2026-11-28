create table if not exists public.chats (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    title text not null default 'New chat',
    active_attachment_ids uuid[] not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    chat_id uuid not null references public.chats (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.attachments (
    id uuid primary key default gen_random_uuid(),
    chat_id uuid not null references public.chats (id) on delete cascade,
    message_id uuid not null references public.messages (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    file_name text not null,
    mime_type text not null,
    size_bytes bigint not null check (size_bytes between 1 and 10485760),
    storage_path text not null unique,
    extracted_text text not null default '',
    created_at timestamptz not null default now()
);

create index if not exists chats_user_updated_idx
    on public.chats (user_id, updated_at desc);
create index if not exists messages_chat_created_idx
    on public.messages (user_id, chat_id, created_at);
create index if not exists attachments_chat_message_idx
    on public.attachments (user_id, chat_id, message_id);

create or replace function public.set_chat_updated_at()
returns trigger
language plpgsql
as $$
begin
    update public.chats set updated_at = now() where id = new.chat_id;
    return new;
end;
$$;

drop trigger if exists messages_touch_chat on public.messages;
create trigger messages_touch_chat
    after insert on public.messages
    for each row execute function public.set_chat_updated_at();

alter table public.chats enable row level security;
alter table public.messages enable row level security;
alter table public.attachments enable row level security;

grant select, insert, update, delete on public.chats to authenticated;
grant select, insert, update, delete on public.messages to authenticated;
grant select, insert, update, delete on public.attachments to authenticated;
revoke all on public.chats, public.messages, public.attachments from anon;

drop policy if exists "Users manage their own chats" on public.chats;
create policy "Users manage their own chats"
    on public.chats for all to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

drop policy if exists "Users manage their own messages" on public.messages;
create policy "Users manage their own messages"
    on public.messages for all to authenticated
    using (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.chats
            where chats.id = messages.chat_id
              and chats.user_id = (select auth.uid())
        )
    )
    with check (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.chats
            where chats.id = messages.chat_id
              and chats.user_id = (select auth.uid())
        )
    );

drop policy if exists "Users manage their own attachment records" on public.attachments;
create policy "Users manage their own attachment records"
    on public.attachments for all to authenticated
    using (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.chats
            where chats.id = attachments.chat_id
              and chats.user_id = (select auth.uid())
        )
    )
    with check (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.chats
            where chats.id = attachments.chat_id
              and chats.user_id = (select auth.uid())
        )
        and exists (
            select 1 from public.messages
            where messages.id = attachments.message_id
              and messages.chat_id = attachments.chat_id
              and messages.user_id = (select auth.uid())
        )
    );

insert into storage.buckets (id, name, public, file_size_limit)
values ('chat-attachments', 'chat-attachments', false, 10485760)
on conflict (id) do update set public = false, file_size_limit = 10485760;

drop policy if exists "Users read their own chat attachments" on storage.objects;
create policy "Users read their own chat attachments"
    on storage.objects for select to authenticated
    using (
        bucket_id = 'chat-attachments'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

drop policy if exists "Users upload their own chat attachments" on storage.objects;
create policy "Users upload their own chat attachments"
    on storage.objects for insert to authenticated
    with check (
        bucket_id = 'chat-attachments'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

drop policy if exists "Users delete their own chat attachments" on storage.objects;
create policy "Users delete their own chat attachments"
    on storage.objects for delete to authenticated
    using (
        bucket_id = 'chat-attachments'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
