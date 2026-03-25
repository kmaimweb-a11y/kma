create extension if not exists pgcrypto;

create table if not exists public.articles (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  summary text,
  image_url text,
  published_at timestamptz,
  category text,
  source_name text not null,
  article_url text not null unique,
  created_at timestamptz not null default now()
);

alter table public.articles
  add column if not exists category text;

create index if not exists idx_articles_published_at
  on public.articles (published_at desc);

create index if not exists idx_articles_source_name
  on public.articles (source_name);

alter table public.articles enable row level security;

drop policy if exists "public can read articles" on public.articles;
create policy "public can read articles"
on public.articles
for select
to anon
using (true);

insert into public.articles (
  title,
  summary,
  image_url,
  published_at,
  category,
  source_name,
  article_url
)
values
(
  'NPU 탑재 온디바이스 AI 공공 서비스 확대 추진',
  '정부가 인터넷 연결 없이 기기 자체에서 작동하는 온디바이스 AI 기반 공공 서비스를 발굴하고 확산하기 위한 사업 공모를 추진합니다.',
  'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=80',
  '2026-03-24T16:20:00+09:00',
  '정부정책',
  '정책브리핑',
  'https://www.korea.kr/news/policyNewsView.do?newsId=148961351&call_from=rsslink'
),
(
  '개인정보위, 생성형 AI 개인정보 처리 안내서 공개',
  '개인정보보호위원회가 생성형 AI 개발·활용을 위한 개인정보 처리 안내서를 공개하고 안전한 활용 기준을 제시했습니다.',
  'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80',
  '2025-08-06T10:00:00+09:00',
  '개인정보·가이드라인',
  '개인정보보호위원회',
  'https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020010000&nttId=11410'
),
(
  '과기정통부, UAE와 AI·첨단산업 협력 강화',
  '과기정통부가 해외 협력과 연계한 AI 및 첨단산업 협력 확대 방향을 발표했습니다.',
  'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=80',
  '2025-11-30T09:00:00+09:00',
  '정부정책',
  '과학기술정보통신부',
  'https://msit.go.kr/bbs/view.do?bbsSeqNo=94&mId=307&mPid=208&nttSeqNo=3186517&sCode=user'
),
(
  '공공부문에서 인공지능(AI) 어떻게 써야해? AI 정부 서비스 사례집에 우수사례 총집합',
  '행정안전부와 한국지능정보사회진흥원이 공공부문 AI 전환 가속화를 위해 AI 정부 서비스 사례집을 발간했습니다.',
  'https://images.unsplash.com/photo-1510511459019-5dda7724fd87?auto=format&fit=crop&w=1200&q=80',
  '2026-03-24T12:00:00+09:00',
  '디지털정부',
  '행정안전부',
  'https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId=124639'
),
(
  '디플정위, 공공부문 초거대 AI 도입·활용 가이드라인 마련',
  '디지털플랫폼정부위원회와 NIA가 중앙부처와 공공기관의 초거대 AI 활용을 위한 가이드라인을 마련했습니다.',
  'https://images.unsplash.com/photo-1516321497487-e288fb19713f?auto=format&fit=crop&w=1200&q=80',
  '2024-04-23T10:30:00+09:00',
  '디지털정부',
  '디지털플랫폼정부위원회',
  'https://dpg.go.kr/DPG/contents/DPG02020000.do?id=20240423103126828477&schBcid=press&schM=view'
),
(
  'KISA, AI 시대 사이버안보 이끌 화이트해커 172명 배출',
  '한국인터넷진흥원이 AI·클라우드 보안 교육과 연계된 차세대 보안 지도자 양성 과정을 소개했습니다.',
  'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80',
  '2026-02-27T10:00:00+09:00',
  'AI보안·신뢰',
  '한국인터넷진흥원',
  'https://www.kisa.or.kr/402/form?postSeq=2576'
)
on conflict (article_url) do nothing;

delete from public.articles a
using public.articles b
where a.id < b.id
  and a.article_url = b.article_url;

update public.articles
set
  title = 'NPU 탑재 온디바이스 AI 공공 서비스 확대 추진',
  summary = '정부가 인터넷 연결 없이 기기 자체에서 작동하는 온디바이스 AI 기반 공공 서비스를 발굴하고 확산하기 위한 사업 공모를 추진합니다.',
  published_at = '2026-03-24T16:20:00+09:00',
  category = '정부정책',
  article_url = 'https://www.korea.kr/news/policyNewsView.do?newsId=148961351&call_from=rsslink'
where source_name = '정책브리핑'
  and article_url = 'https://www.korea.kr/'
  and not exists (
    select 1
    from public.articles x
    where x.article_url = 'https://www.korea.kr/news/policyNewsView.do?newsId=148961351&call_from=rsslink'
  );

update public.articles
set
  title = '공공부문에서 인공지능(AI) 어떻게 써야해? AI 정부 서비스 사례집에 우수사례 총집합',
  summary = '행정안전부와 한국지능정보사회진흥원이 공공부문 AI 전환 가속화를 위해 AI 정부 서비스 사례집을 발간했습니다.',
  published_at = '2026-03-24T12:00:00+09:00',
  category = '디지털정부',
  article_url = 'https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId=124639'
where source_name = '행정안전부'
  and article_url like '%rss.jsp%'
  and not exists (
    select 1
    from public.articles x
    where x.article_url = 'https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId=124639'
  );

update public.articles
set article_url = replace(article_url, 'http://www.kisa.or.kr/', 'https://www.kisa.or.kr/')
where source_name = '한국인터넷진흥원'
  and article_url like 'http://www.kisa.or.kr/%'
  and not exists (
    select 1
    from public.articles x
    where x.article_url = replace(public.articles.article_url, 'http://www.kisa.or.kr/', 'https://www.kisa.or.kr/')
  );
