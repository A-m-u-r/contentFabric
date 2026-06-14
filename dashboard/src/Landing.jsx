import React from 'react';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  Cpu,
  FileVideo,
  Gauge,
  Globe2,
  Instagram,
  KeyRound,
  Languages,
  Megaphone,
  Play,
  Repeat2,
  Send,
  Sparkles,
  Subtitles,
  UserRound,
  Youtube,
  Zap,
} from 'lucide-react';

const TikTokIcon = ({ size = 18, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743 2.895 2.895 0 0 1 3.183-4.51v-3.5a6.329 6.329 0 0 0-5.394 10.692 6.33 6.33 0 0 0 10.857-4.424V8.687a8.182 8.182 0 0 0 4.773 1.526V6.79a4.831 4.831 0 0 1-1.003-.104Z" />
  </svg>
);

const LANDING_COPY = {
  ru: {
    nav: {
      product: 'Возможности',
      pipeline: 'Пайплайн',
      pricing: 'Доступ',
      faq: 'FAQ',
      login: 'Войти',
    },
    hero: {
      eyebrow: 'ИИ content factory для коротких видео',
      title: 'От идеи до Reels, Shorts и заявок в одном пайплайне',
      description:
        'Платформа полного цикла для ежедневного производства коротких роликов: идея, сценарий, AI-актер, озвучка, lip-sync, субтитры, публикация, аналитика и новые гипотезы.',
      primary: 'Открыть платформу',
      secondary: 'Посмотреть процесс',
      note: 'Подписка дает доступ к платформенным лимитам. При желании можно подключить свои API для Gemini, fal.ai, ElevenLabs и публикации.',
    },
    stats: [
      { value: '30+', label: 'роликов в месяц на одну нишу' },
      { value: '3', label: 'канала: TikTok, Instagram, YouTube' },
      { value: 'BYOK', label: 'режим со своими API-ключами' },
    ],
    productCards: [
      {
        icon: Bot,
        title: 'AI Shorts',
        text: 'Генерация UGC-роликов с AI-актером, голосом, lip-sync, hooks, captions и субтитрами.',
        points: ['AI-актеры и свои аватары', 'Kling/Hailuo/lip-sync режимы', 'Русская озвучка и субтитры'],
      },
      {
        icon: FileVideo,
        title: 'Clip Factory',
        text: 'Пересборка длинных видео в короткие вертикальные клипы для Reels, Shorts и TikTok.',
        points: ['поиск сильных моментов', '9:16 кадрирование', 'автосубтитры и hook overlays'],
      },
      {
        icon: Youtube,
        title: 'YouTube Studio',
        text: 'Вспомогательный блок для названий, описаний, обложек и публикации контента.',
        points: ['идеи заголовков', 'описания с таймкодами', 'публикация в соцсети'],
      },
    ],
    pipelineTitle: 'Полный цикл контент-завода',
    pipelineText:
      'Система не заканчивается на генерации видео. Она помогает связать производство, публикацию, реакцию аудитории и новые гипотезы.',
    pipeline: [
      'Идея',
      'Сценарий',
      'AI-актер',
      'Видео',
      'Публикация',
      'Аналитика',
      'Лиды',
      'Новые гипотезы',
    ],
    channelsTitle: 'Собрано под ежедневный постинг',
    channelsText:
      'Один сценарий можно адаптировать под TikTok, Instagram Reels и YouTube Shorts без ручной пересборки каждого ролика.',
    features: [
      { icon: Sparkles, title: 'Сценарии и hooks', text: 'Генерация сценариев под нишу, оффер, аудиторию и формат ролика.' },
      { icon: UserRound, title: 'AI-актеры', text: 'Загрузка своих аватаров или генерация новых лиц для UGC-подачи.' },
      { icon: Subtitles, title: 'Субтитры', text: 'Короткие читаемые субтитры и hook-тексты для удержания внимания.' },
      { icon: Send, title: 'Публикация', text: 'Экспорт или публикация в TikTok, Instagram и YouTube из одного интерфейса.' },
      { icon: BarChart3, title: 'Аналитика', text: 'Сравнение тем, hooks и CTA, чтобы наращивать удачные гипотезы.' },
      { icon: KeyRound, title: 'Свои API', text: 'Можно работать на подписке платформы или подключить свои API-ключи.' },
    ],
    access: {
      title: 'Подписка плюс контроль над API',
      text:
        'Мы продаем доступ к рабочему интерфейсу и пайплайну. Для команд, которые хотят контролировать расходы напрямую, остается режим со своими API.',
      leftTitle: 'Подписка',
      leftPoints: ['быстрый старт без сборки инфраструктуры', 'единая галерея роликов и аватаров', 'готовые режимы качества и стоимости'],
      rightTitle: 'свои API',
      rightPoints: ['Gemini для анализа и сценариев', 'fal.ai для видео, аватаров и lip-sync', 'ElevenLabs для голоса', 'Upload-Post для публикаций'],
    },
    faq: [
      {
        question: 'Это генератор роликов или полноценная контент-фабрика?',
        answer:
          'Главная идея именно в фабрике полного цикла: не просто сделать видео, а пройти путь от идеи и сценария до публикации, аналитики и следующей гипотезы.',
      },
      {
        question: 'Можно ли использовать русский язык?',
        answer:
          'Да. Лендинг по умолчанию показывает русский, а внутри пайплайна поддерживаются русские сценарии, озвучка и субтитры при наличии подходящих ключей и голосов.',
      },
      {
        question: 'Зачем нужны свои API, если есть подписка?',
        answer:
          'Подписка нужна для доступа к продукту и готовому workflow. Свои API полезны, если ты хочешь платить провайдерам напрямую, тестировать другие лимиты или контролировать расходы по каждому сервису.',
      },
      {
        question: 'Для кого это подходит?',
        answer:
          'Для экспертов, малых бизнесов, агентств и проектов, которым нужен стабильный поток коротких роликов, а не разовая генерация ради теста.',
      },
    ],
    finalCta: {
      title: 'Запусти первую производственную линию контента',
      text: 'Начни с одной ниши, одного оффера и 7-10 роликов. Дальше система покажет, какие темы стоит масштабировать.',
      button: 'Перейти в приложение',
    },
  },
  en: {
    nav: {
      product: 'Product',
      pipeline: 'Pipeline',
      pricing: 'Access',
      faq: 'FAQ',
      login: 'Open app',
    },
    hero: {
      eyebrow: 'AI content factory for short-form video',
      title: 'From idea to Reels, Shorts and leads in one pipeline',
      description:
        'A full-cycle platform for daily short-form production: idea, script, AI actor, voiceover, lip-sync, captions, publishing, analytics and the next content hypothesis.',
      primary: 'Open platform',
      secondary: 'See workflow',
      note: 'Subscription access includes platform limits. Teams can also connect their own APIs for Gemini, fal.ai, ElevenLabs and publishing.',
    },
    stats: [
      { value: '30+', label: 'videos per month per niche' },
      { value: '3', label: 'channels: TikTok, Instagram, YouTube' },
      { value: 'BYOK', label: 'bring your own API keys' },
    ],
    productCards: [
      {
        icon: Bot,
        title: 'AI Shorts',
        text: 'Generate UGC-style videos with AI actors, voiceover, lip-sync, hooks, captions and subtitles.',
        points: ['AI actors and custom avatars', 'Kling, Hailuo and lip-sync modes', 'Multilingual voice and captions'],
      },
      {
        icon: FileVideo,
        title: 'Clip Factory',
        text: 'Turn long videos into vertical clips for Reels, Shorts and TikTok.',
        points: ['strong moment detection', '9:16 reframing', 'subtitles and hook overlays'],
      },
      {
        icon: Youtube,
        title: 'YouTube Studio',
        text: 'Support tools for titles, descriptions, thumbnails and publishing.',
        points: ['title ideas', 'descriptions with timestamps', 'social publishing'],
      },
    ],
    pipelineTitle: 'The full content-factory cycle',
    pipelineText:
      'The product does not stop at video generation. It connects production, publishing, audience response and the next set of tests.',
    pipeline: ['Idea', 'Script', 'AI actor', 'Video', 'Publish', 'Analytics', 'Lead', 'New hypothesis'],
    channelsTitle: 'Built for daily posting',
    channelsText:
      'One script can be adapted for TikTok, Instagram Reels and YouTube Shorts without manually rebuilding every video.',
    features: [
      { icon: Sparkles, title: 'Scripts and hooks', text: 'Generate scripts for a niche, offer, audience and short-form format.' },
      { icon: UserRound, title: 'AI actors', text: 'Upload your own avatars or generate new faces for UGC-style delivery.' },
      { icon: Subtitles, title: 'Captions', text: 'Readable subtitles and hook overlays for retention.' },
      { icon: Send, title: 'Publishing', text: 'Export or publish to TikTok, Instagram and YouTube from one interface.' },
      { icon: BarChart3, title: 'Analytics', text: 'Compare topics, hooks and CTAs to scale stronger hypotheses.' },
      { icon: KeyRound, title: 'Your APIs', text: 'Use platform subscription limits or connect your own API keys.' },
    ],
    access: {
      title: 'Subscription plus API control',
      text:
        'We sell access to the working interface and pipeline. Teams that want direct cost control can connect their own provider accounts.',
      leftTitle: 'Subscription',
      leftPoints: ['start without building infrastructure', 'one gallery for videos and avatars', 'ready cost and quality modes'],
      rightTitle: 'your APIs',
      rightPoints: ['Gemini for analysis and scripts', 'fal.ai for video, avatars and lip-sync', 'ElevenLabs for voice', 'Upload-Post for publishing'],
    },
    faq: [
      {
        question: 'Is this a video generator or a full content factory?',
        answer:
          'The core idea is the full factory: move from idea and script to publishing, analytics and the next hypothesis, not just one video export.',
      },
      {
        question: 'Does it support Russian?',
        answer:
          'Yes. Russian is the default landing language, and the production pipeline can use Russian scripts, voices and subtitles when the right keys and voices are configured.',
      },
      {
        question: 'Why connect my own APIs if I have a subscription?',
        answer:
          'Subscription gives access to the product and workflow. Your own APIs are useful when you want to pay providers directly, test different limits or control spend per service.',
      },
      {
        question: 'Who is it for?',
        answer:
          'Experts, small businesses, agencies and projects that need a steady stream of short-form content rather than a one-off generation test.',
      },
    ],
    finalCta: {
      title: 'Launch your first content production line',
      text: 'Start with one niche, one offer and 7-10 videos. Then scale the topics that show traction.',
      button: 'Open the app',
    },
  },
};

const getInitialLanguage = () => {
  if (typeof navigator === 'undefined') return 'ru';
  return navigator.language?.toLowerCase().startsWith('en') ? 'en' : 'ru';
};

const SectionHeading = ({ eyebrow, title, text }) => (
  <div className="mb-10 max-w-3xl">
    {eyebrow && <p className="mb-3 text-sm font-semibold text-cyan-300">{eyebrow}</p>}
    <h2 className="text-3xl font-bold tracking-tight text-white md:text-4xl">{title}</h2>
    {text && <p className="mt-4 text-base leading-7 text-zinc-400">{text}</p>}
  </div>
);

const ServiceBadge = ({ icon: Icon, label, tone = 'cyan' }) => {
  const tones = {
    cyan: 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100',
    pink: 'border-pink-300/25 bg-pink-300/10 text-pink-100',
    amber: 'border-amber-300/25 bg-amber-300/10 text-amber-100',
    blue: 'border-blue-300/25 bg-blue-300/10 text-blue-100',
  };
  return (
    <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${tones[tone]}`}>
      <Icon size={17} />
      <span>{label}</span>
    </div>
  );
};

const ProductCard = ({ icon: Icon, title, text, points }) => (
  <article className="rounded-xl border border-white/10 bg-zinc-950/55 p-6 shadow-[0_18px_80px_rgba(0,0,0,0.22)] backdrop-blur">
    <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg bg-white/10">
      <Icon size={22} className="text-cyan-200" />
    </div>
    <h3 className="text-xl font-bold text-white">{title}</h3>
    <p className="mt-3 text-sm leading-6 text-zinc-400">{text}</p>
    <ul className="mt-5 space-y-2">
      {points.map((point) => (
        <li key={point} className="flex gap-2 text-sm text-zinc-300">
          <Check size={15} className="mt-0.5 shrink-0 text-emerald-300" />
          <span>{point}</span>
        </li>
      ))}
    </ul>
  </article>
);

const FeatureRow = ({ icon: Icon, title, text }) => (
  <div className="flex gap-4 rounded-xl border border-white/10 bg-white/[0.035] p-5">
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-cyan-300/10 text-cyan-200">
      <Icon size={20} />
    </div>
    <div>
      <h3 className="font-semibold text-white">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-zinc-400">{text}</p>
    </div>
  </div>
);

const FAQItem = ({ question, answer, isOpen, onClick }) => (
  <div className="rounded-xl border border-white/10 bg-zinc-950/45">
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-white"
    >
      <span className="font-medium">{question}</span>
      <ChevronDown size={18} className={`shrink-0 text-zinc-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
    </button>
    {isOpen && <p className="px-5 pb-5 text-sm leading-6 text-zinc-400">{answer}</p>}
  </div>
);

function FactoryPreview({ copy }) {
  return (
    <div className="pointer-events-none absolute inset-x-4 bottom-0 hidden translate-y-[42%] md:block">
      <div className="mx-auto max-w-5xl rounded-xl border border-white/10 bg-zinc-950/75 p-4 shadow-[0_30px_120px_rgba(0,0,0,0.45)] backdrop-blur-xl">
        <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500">Content line</p>
                <p className="font-semibold text-white">START 7 / Reels sprint</p>
              </div>
              <div className="rounded-md border border-emerald-300/25 bg-emerald-300/10 px-2 py-1 text-xs text-emerald-200">ready</div>
            </div>
            <div className="grid grid-cols-4 gap-2 text-xs text-zinc-300">
              {copy.pipeline.slice(0, 4).map((step, index) => (
                <div key={step} className="rounded-md border border-white/10 bg-zinc-900/80 p-3">
                  <span className="mb-2 block text-zinc-500">0{index + 1}</span>
                  {step}
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-300/20 to-pink-300/20">
                <Play size={20} className="text-white" />
              </div>
              <div>
                <p className="font-semibold text-white">Reel batch</p>
                <p className="text-xs text-zinc-500">TikTok / Instagram / YouTube</p>
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-cyan-300 via-fuchsia-300 to-amber-200" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Landing({ onLaunchApp }) {
  const [language, setLanguage] = React.useState(getInitialLanguage);
  const [openFaq, setOpenFaq] = React.useState(0);
  const copy = LANDING_COPY[language] || LANDING_COPY.ru;

  return (
    <div className="min-h-screen overflow-hidden bg-[#07080d] text-white">
      <div className="pointer-events-none fixed inset-0 -z-10 aurora-mesh" />

      <nav className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-[#07080d]/78 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <a href="#" className="flex items-center gap-3">
            <img src="/logo-openshorts.png" alt="Content Factory logo" className="h-8 w-8" />
            <span className="font-bold tracking-tight">AI Content Factory</span>
          </a>
          <div className="hidden items-center gap-7 text-sm text-zinc-400 md:flex">
            <a href="#product" className="hover:text-white">{copy.nav.product}</a>
            <a href="#pipeline" className="hover:text-white">{copy.nav.pipeline}</a>
            <a href="#access" className="hover:text-white">{copy.nav.pricing}</a>
            <a href="#faq" className="hover:text-white">{copy.nav.faq}</a>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden rounded-lg border border-white/10 bg-white/5 p-1 sm:flex">
              {['ru', 'en'].map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => setLanguage(lang)}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                    language === lang ? 'bg-white text-zinc-950' : 'text-zinc-400 hover:text-white'
                  }`}
                >
                  {lang.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onLaunchApp}
              className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:-translate-y-0.5 hover:bg-cyan-100"
            >
              {copy.nav.login}
            </button>
          </div>
        </div>
      </nav>

      <header className="relative min-h-[100dvh] px-5 pb-40 pt-32 md:pb-52">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_50%_0%,rgba(0,128,255,0.22),transparent_34%),linear-gradient(180deg,rgba(7,8,13,0.05),#07080d_88%)]" />
        <div className="mx-auto max-w-7xl">
          <div className="max-w-4xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-sm text-cyan-100">
              <Sparkles size={16} />
              <span>{copy.hero.eyebrow}</span>
            </div>
            <h1 className="max-w-5xl text-4xl font-bold tracking-tight text-white md:text-6xl lg:text-7xl">
              {copy.hero.title}
            </h1>
            <p className="hero-description mt-7 max-w-3xl text-lg leading-8 text-zinc-300 md:text-xl">
              {copy.hero.description}
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={onLaunchApp}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-300 to-amber-200 px-6 py-3.5 font-semibold text-zinc-950 transition hover:-translate-y-0.5"
              >
                {copy.hero.primary}
                <ArrowRight size={19} />
              </button>
              <a
                href="#pipeline"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-6 py-3.5 font-semibold text-white transition hover:bg-white/10"
              >
                <Gauge size={18} />
                {copy.hero.secondary}
              </a>
            </div>
            <p className="mt-5 max-w-3xl text-sm leading-6 text-zinc-500">{copy.hero.note}</p>
          </div>

          <div className="mt-12 flex flex-wrap gap-3">
            <ServiceBadge icon={Cpu} label="Gemini" tone="blue" />
            <ServiceBadge icon={Zap} label="fal.ai" tone="amber" />
            <ServiceBadge icon={Languages} label="ElevenLabs" tone="pink" />
            <ServiceBadge icon={TikTokIcon} label="TikTok" tone="cyan" />
            <ServiceBadge icon={Instagram} label="Instagram" tone="pink" />
            <ServiceBadge icon={Youtube} label="YouTube" tone="amber" />
          </div>

          <div className="mt-12 grid max-w-4xl gap-3 sm:grid-cols-3">
            {copy.stats.map((stat) => (
              <div key={stat.label} className="rounded-xl border border-white/10 bg-white/[0.045] p-4 backdrop-blur">
                <p className="text-2xl font-bold text-white">{stat.value}</p>
                <p className="mt-1 text-sm text-zinc-400">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
        <FactoryPreview copy={copy} />
      </header>

      <main>
        <section id="product" className="px-5 py-20 md:pt-28">
          <div className="mx-auto max-w-7xl">
            <SectionHeading title={copy.channelsTitle} text={copy.channelsText} />
            <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="grid gap-5 md:grid-cols-2">
                {copy.productCards.slice(0, 2).map((card) => (
                  <ProductCard key={card.title} {...card} />
                ))}
              </div>
              <ProductCard {...copy.productCards[2]} />
            </div>
          </div>
        </section>

        <section id="pipeline" className="px-5 py-20">
          <div className="mx-auto max-w-7xl">
            <SectionHeading title={copy.pipelineTitle} text={copy.pipelineText} />
            <div className="rounded-xl border border-white/10 bg-zinc-950/55 p-5 backdrop-blur">
              <div className="grid gap-3 md:grid-cols-4">
                {copy.pipeline.map((step, index) => (
                  <div key={step} className="relative rounded-lg border border-white/10 bg-white/[0.035] p-4">
                    <span className="mb-6 block text-xs font-semibold text-zinc-500">{String(index + 1).padStart(2, '0')}</span>
                    <p className="font-semibold text-white">{step}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="px-5 py-20">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
            <div>
              <SectionHeading
                eyebrow="Workflow"
                title={language === 'ru' ? 'Один интерфейс вместо набора разрозненных сервисов' : 'One interface instead of scattered tools'}
                text={
                  language === 'ru'
                    ? 'Пользователь видит не набор API, а понятные производственные этапы: сценарий, видео, озвучка, публикация, результат.'
                    : 'Users see a production workflow rather than a pile of provider APIs: script, video, voice, publishing and result.'
                }
              />
              <div className="mt-6 rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-5 text-sm leading-6 text-cyan-50">
                {language === 'ru'
                  ? 'Главная ценность не в одной генерации, а в повторяемости: каждый день выпускать ролики, сравнивать результаты и быстро менять гипотезы.'
                  : 'The core value is repeatability: publish videos every day, compare results and change hypotheses quickly.'}
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {copy.features.map((feature) => (
                <FeatureRow key={feature.title} {...feature} />
              ))}
            </div>
          </div>
        </section>

        <section id="access" className="px-5 py-20">
          <div className="mx-auto max-w-7xl">
            <SectionHeading title={copy.access.title} text={copy.access.text} />
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-xl border border-amber-200/20 bg-amber-200/10 p-6">
                <div className="mb-5 flex items-center gap-3">
                  <Megaphone size={22} className="text-amber-100" />
                  <h3 className="text-xl font-bold text-white">{copy.access.leftTitle}</h3>
                </div>
                <ul className="space-y-3">
                  {copy.access.leftPoints.map((point) => (
                    <li key={point} className="flex gap-2 text-sm text-zinc-300">
                      <Check size={15} className="mt-0.5 shrink-0 text-amber-100" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-6">
                <div className="mb-5 flex items-center gap-3">
                  <KeyRound size={22} className="text-cyan-100" />
                  <h3 className="text-xl font-bold text-white">{copy.access.rightTitle}</h3>
                </div>
                <ul className="space-y-3">
                  {copy.access.rightPoints.map((point) => (
                    <li key={point} className="flex gap-2 text-sm text-zinc-300">
                      <Check size={15} className="mt-0.5 shrink-0 text-cyan-100" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="px-5 py-20">
          <div className="mx-auto max-w-7xl rounded-xl border border-white/10 bg-zinc-950/60 p-6 md:p-8">
            <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
              <div>
                <div className="mb-4 inline-flex items-center gap-2 rounded-lg border border-pink-300/20 bg-pink-300/10 px-3 py-2 text-sm text-pink-100">
                  <Repeat2 size={16} />
                  {language === 'ru' ? 'Цикл гипотез' : 'Hypothesis loop'}
                </div>
                <h2 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
                  {language === 'ru' ? 'Контент должен улучшаться после публикации' : 'Content should improve after publishing'}
                </h2>
                <p className="mt-4 text-base leading-7 text-zinc-400">
                  {language === 'ru'
                    ? 'Смысл фабрики в том, чтобы темы, hooks, аватары, CTA и форматы не угадывались один раз, а постоянно уточнялись по реакции аудитории.'
                    : 'The point of the factory is to keep improving topics, hooks, actors, CTAs and formats based on audience response.'}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { icon: Play, label: language === 'ru' ? 'ролики' : 'videos' },
                  { icon: BarChart3, label: language === 'ru' ? 'сигналы' : 'signals' },
                  { icon: Sparkles, label: language === 'ru' ? 'новые идеи' : 'new ideas' },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                    <item.icon size={22} className="mb-8 text-cyan-200" />
                    <p className="font-semibold text-white">{item.label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="faq" className="px-5 py-20">
          <div className="mx-auto max-w-3xl">
            <SectionHeading title={copy.nav.faq} text={language === 'ru' ? 'Коротко о том, как это позиционировать и использовать.' : 'Short answers on positioning and usage.'} />
            <div className="space-y-3">
              {copy.faq.map((faq, index) => (
                <FAQItem
                  key={faq.question}
                  question={faq.question}
                  answer={faq.answer}
                  isOpen={openFaq === index}
                  onClick={() => setOpenFaq(openFaq === index ? null : index)}
                />
              ))}
            </div>
          </div>
        </section>

        <section className="px-5 py-20">
          <div className="mx-auto max-w-5xl text-center">
            <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-300/20 to-amber-200/20">
              <Globe2 size={24} className="text-cyan-100" />
            </div>
            <h2 className="text-3xl font-bold tracking-tight text-white md:text-5xl">{copy.finalCta.title}</h2>
            <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-zinc-400">{copy.finalCta.text}</p>
            <button
              type="button"
              onClick={onLaunchApp}
              className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-7 py-3.5 font-semibold text-zinc-950 transition hover:-translate-y-0.5 hover:bg-cyan-100"
            >
              {copy.finalCta.button}
              <ArrowRight size={19} />
            </button>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 px-5 py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 text-sm text-zinc-500 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo-openshorts.png" alt="AI Content Factory" className="h-6 w-6" />
            <span>AI Content Factory</span>
          </div>
          <div className="flex flex-wrap gap-5">
            <a href="#product" className="hover:text-white">{copy.nav.product}</a>
            <a href="#pipeline" className="hover:text-white">{copy.nav.pipeline}</a>
            <a href="#access" className="hover:text-white">{copy.nav.pricing}</a>
            <a href="#legal" className="hover:text-white">Legal</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
