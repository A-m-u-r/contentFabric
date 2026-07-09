import React from 'react';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  FileVideo,
  Gauge,
  Globe2,
  Instagram,
  KeyRound,
  Megaphone,
  Moon,
  Play,
  Repeat2,
  Send,
  Sparkles,
  Subtitles,
  Sun,
  UserRound,
  Youtube,
} from 'lucide-react';

const TikTokIcon = ({ size = 18, className = '' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743 2.895 2.895 0 0 1 3.183-4.51v-3.5a6.329 6.329 0 0 0-5.394 10.692 6.33 6.33 0 0 0 10.857-4.424V8.687a8.182 8.182 0 0 0 4.773 1.526V6.79a4.831 4.831 0 0 1-1.003-.104Z" />
  </svg>
);

const BRAND_NAME = 'OpenShorts';
const BRAND_ICON = '/favicon-192.png';

const LANDING_COPY = {
  ru: {
    nav: {
      product: 'Что собирает',
      pipeline: 'Петля',
      pricing: 'Доступ',
      faq: 'FAQ',
      login: 'Собрать серию',
      legal: 'Документы',
    },
    hero: {
      eyebrow: 'OpenShorts / series engine',
      title: '10 AI-роликов из одного оффера — за один запуск',
      description:
        'Задайте продукт, нишу или URL. OpenShorts разложит оффер на hooks, соберет сценарии, AI-аватара, голос, субтитры, публикацию и сигналы для следующей серии.',
      primary: 'Собрать тестовую серию',
      secondary: 'Забрать карту hooks',
      note: 'Первый шаг - не один идеальный ролик, а пачка гипотез на 7-10 видео. Свои API можно подключить для контроля себестоимости генерации.',
    },
    heroMockup: {
      lineLabel: 'Пульт серии',
      campaign: 'Оффер: консультация по питанию',
      status: 'новая версия',
      idea: '1 оффер',
      script: '25 hooks + 10 сценариев',
      avatar: 'UGC-аватар + голос + lip-sync',
      output: 'Reels / Shorts / TikTok',
      queue: 'Очередь на 3 площадки',
      analytics: 'удержание',
      leads: 'DM / заявки',
      hypothesis: 'следующая связка',
      hooks: ['Боль в первые 2 секунды', 'До / после без обещаний', 'Оффер через личную историю'],
      signals: ['42% удержание', '5 DM', '2 заявки'],
    },
    capabilities: [
      { icon: Sparkles, label: 'Оффер' },
      { icon: Bot, label: 'Hooks' },
      { icon: UserRound, label: 'AI-аватар' },
      { icon: Megaphone, label: 'Голос' },
      { icon: Subtitles, label: 'Субтитры' },
      { icon: Send, label: 'Публикация' },
    ],
    proofPoints: [
      { title: '10 роликов', text: 'пакет под одну гипотезу' },
      { title: '1 запуск', text: 'оффер, hooks, аватар, публикация' },
      { title: '3 канала', text: 'Reels, Shorts и TikTok' },
    ],
    leadMagnet: {
      eyebrow: 'Лид-магнит для холодного трафика',
      title: 'Карта из 25 hooks для первой серии',
      text:
        'Быстрый вход без брифа: выберите нишу, боль аудитории и получите стартовые углы подачи для Reels, Shorts и TikTok.',
      items: ['5 типов боли для первых секунд', 'формулы hooks без кликбейта', 'мини-бриф для первой серии', 'CTA под DM, заявку или переход'],
      inputLabel: 'Email для карты hooks',
      placeholder: 'email@company.ru',
      button: 'Получить карту hooks',
      note: 'Форма готова под подключение рассылки. Сейчас кнопка ведет в сборку серии.',
    },
    productCards: [
      {
        icon: Sparkles,
        title: 'Разбор оффера',
        text: 'Система превращает продукт, услугу или URL в набор углов подачи для коротких видео.',
        points: ['боли и желания аудитории', 'hooks для первых секунд', 'варианты CTA под лиды или заявки'],
      },
      {
        icon: FileVideo,
        title: 'Производство серии',
        text: 'Из выбранных hooks собираются сценарии, вертикальные ролики, озвучка, lip-sync и субтитры.',
        points: ['AI-аватар или свой персонаж', 'голос, b-roll и субтитры', 'пакет роликов вместо одиночной генерации'],
      },
      {
        icon: BarChart3,
        title: 'Публикация и сигналы',
        text: 'Ролики уходят в очередь публикаций, а реакции возвращаются в следующую гипотезу.',
        points: ['очередь TikTok, Reels и Shorts', 'сравнение hooks и CTA', 'идеи для следующей серии'],
      },
    ],
    pipelineTitle: 'Петля роста: оффер → серия → сигнал',
    pipelineText:
      'Не угадывайте один идеальный ролик. Выпускайте маленькую серию, смотрите удержание, DM и заявки, затем размножайте только те углы, где появился сигнал.',
    pipeline: [
      'Оффер',
      'Hooks',
      'AI-актер',
      'Видео',
      'Публикация',
      'Удержание',
      'DM / лиды',
      'Новая серия',
    ],
    pipelineGroups: [
      {
        key: 'idea',
        title: 'Оффер',
        text: 'Формулируем аудиторию, обещание, боль и несколько углов подачи, которые можно быстро проверить.',
        steps: [0, 1],
      },
      {
        key: 'video',
        title: 'Серия',
        text: 'Собираем ролики с аватаром, голосом, субтитрами и выпуском под нужные площадки.',
        steps: [2, 3, 4],
      },
      {
        key: 'reaction',
        title: 'Сигнал',
        text: 'Сравниваем удержание, DM, лиды и сохраняем связки, которые стоит масштабировать.',
        steps: [5, 6, 7],
      },
    ],
    pipelineConnectorLabels: ['пакет готов', 'серия опубликована'],
    pipelineReturn: 'Сигналы → новая серия',
    pipelineReturnText: 'Удержание, DM, клики, заявки и сохранения становятся брифом для следующего выпуска.',
    pipelineSignals: ['удержание', 'DM', 'клики', 'заявки'],
    channelsTitle: 'Внутри не генератор, а линия выпуска',
    channelsText:
      'Обычно такую серию приходится собирать из ChatGPT, сервиса аватаров, голоса, монтажки и автопостинга. Здесь это один поток: оффер, hooks, ролики, публикация, сигналы.',
    features: [
      { icon: Sparkles, title: 'Пакет сценариев', text: 'Несколько hooks и сценариев под один оффер, чтобы тестировать не вслепую.' },
      { icon: UserRound, title: 'AI-аватар', text: 'UGC-подача через AI-персонажа или загруженный образ для узнаваемой серии.' },
      { icon: Repeat2, title: 'Голос и lip-sync', text: 'Озвучка, синхронизация губ и варианты подачи без ручного сведения.' },
      { icon: Subtitles, title: 'Субтитры', text: 'Короткие читаемые титры и hook-оверлеи для удержания первых секунд.' },
      { icon: Send, title: 'Автопостинг', text: 'Очередь публикаций под TikTok, Instagram Reels и YouTube Shorts.' },
      { icon: KeyRound, title: 'Себестоимость', text: 'Подписка для старта или свои API-ключи, если нужно контролировать расходы.' },
    ],
    access: {
      title: 'Подписка на кабинет + контроль себестоимости',
      text:
        'Платформа продает рабочий кабинет для выпуска серий. Если объемы растут, можно подключить свои ключи и видеть, где именно расходуется бюджет.',
      leftTitle: 'Старт на подписке',
      leftPoints: ['не нужно собирать инфраструктуру из пяти сервисов', 'в одном месте брифы, сценарии, ролики и очередь', 'понятный путь от оффера до первой серии'],
      rightTitle: 'Свои API',
      rightPoints: ['Gemini для анализа оффера и сценариев', 'fal.ai для видео, аватаров и lip-sync', 'ElevenLabs для голоса', 'Upload-Post для публикаций'],
    },
    faq: [
      {
        question: 'Почему серия лучше одного ролика?',
        answer:
          'Один ролик легко промахивается по боли, hook или подаче. Серия из 7-10 роликов быстрее показывает, какие углы цепляют аудиторию и что стоит масштабировать.',
      },
      {
        question: 'Можно ли делать ролики на русском?',
        answer:
          'Да. Сценарии, озвучку, титры и подачу можно собирать на русском, если выбранные модели и голоса поддерживают нужный язык.',
      },
      {
        question: 'Зачем нужны свои API, если есть подписка?',
        answer:
          'Подписка дает кабинет и workflow. Свои API нужны тем, кто делает много роликов, хочет платить провайдерам напрямую и видеть себестоимость по видео, голосу и публикации.',
      },
      {
        question: 'Для кого это подходит?',
        answer:
          'Для экспертов, малого бизнеса, агентств и проектов, где нужно регулярно проверять офферы, лид-магниты, продукты или консультации через короткие видео.',
      },
      {
        question: 'Сколько ручной работы остается?',
        answer:
          'Нужно задать нишу, продукт, ограничения и выбрать удачные варианты. Ручная склейка между сценариями, аватаром, голосом, субтитрами и публикацией уходит в пайплайн.',
      },
    ],
    finalCta: {
      title: 'Запустите первую серию, а не один ролик',
      text: 'Начните с одного оффера и 7-10 коротких видео. Дальше сравните реакции и оставьте только те связки, которые дают сигнал.',
      button: 'Собрать тестовую серию',
    },
  },
  en: {
    nav: {
      product: 'What it builds',
      pipeline: 'Loop',
      pricing: 'Access',
      faq: 'FAQ',
      login: 'Build a series',
      legal: 'Legal',
    },
    hero: {
      eyebrow: 'OpenShorts / series engine',
      title: '10 AI videos from one offer in one run',
      description:
        'Give OpenShorts a product, niche or URL. It turns the offer into hooks, scripts, an AI avatar, voice, captions, publishing and the signals for the next batch.',
      primary: 'Build a test series',
      secondary: 'Get hook map',
      note: 'Start with a 7-10 video hypothesis batch, not one perfect clip. Connect your own APIs when you need direct cost control.',
    },
    heroMockup: {
      lineLabel: 'Series console',
      campaign: 'Offer: nutrition consult',
      status: 'new version',
      idea: '1 offer',
      script: '25 hooks + 10 scripts',
      avatar: 'UGC avatar + voice + lip-sync',
      output: 'Reels / Shorts / TikTok',
      queue: 'Queue for 3 channels',
      analytics: 'retention',
      leads: 'DM / leads',
      hypothesis: 'next angle',
      hooks: ['Pain in first 2 seconds', 'Before / after without hype', 'Offer through a personal story'],
      signals: ['42% retention', '5 DMs', '2 leads'],
    },
    capabilities: [
      { icon: Sparkles, label: 'Offer' },
      { icon: Bot, label: 'Hooks' },
      { icon: UserRound, label: 'AI avatar' },
      { icon: Megaphone, label: 'Voice' },
      { icon: Subtitles, label: 'Captions' },
      { icon: Send, label: 'Publishing' },
    ],
    proofPoints: [
      { title: '10 videos', text: 'one hypothesis batch' },
      { title: '1 run', text: 'offer, hooks, avatar, publishing' },
      { title: '3 channels', text: 'Reels, Shorts and TikTok' },
    ],
    leadMagnet: {
      eyebrow: 'Lead magnet for cold traffic',
      title: '25-hook map for the first series',
      text:
        'A fast starting point without a long brief: pick a niche and audience pain, then use proven short-form angles for Reels, Shorts and TikTok.',
      items: ['5 pain types for the first seconds', 'hook formulas without clickbait', 'mini brief for the first batch', 'CTAs for DMs, leads or clicks'],
      inputLabel: 'Email for the hook map',
      placeholder: 'email@company.com',
      button: 'Get the hook map',
      note: 'The capture form is ready for email integration. For now it opens the series builder.',
    },
    productCards: [
      {
        icon: Sparkles,
        title: 'Offer breakdown',
        text: 'Turn a product, service or URL into angles for short-form video tests.',
        points: ['audience pains and desires', 'first-second hooks', 'CTA variants for leads or DMs'],
      },
      {
        icon: FileVideo,
        title: 'Series production',
        text: 'Build scripts, vertical clips, voice, lip-sync and captions from the selected hooks.',
        points: ['AI avatar or owned character', 'voice, b-roll and subtitles', 'a batch instead of one-off generation'],
      },
      {
        icon: BarChart3,
        title: 'Publishing and signals',
        text: 'Send videos to the publishing queue and bring response back into the next hypothesis.',
        points: ['TikTok, Reels and Shorts queue', 'hook and CTA comparison', 'ideas for the next batch'],
      },
    ],
    pipelineTitle: 'Growth loop: offer → series → signal',
    pipelineText:
      'Stop guessing the one perfect clip. Publish a small series, read retention, DMs and leads, then scale the angles that show signal.',
    pipeline: ['Offer', 'Hooks', 'AI actor', 'Video', 'Publish', 'Retention', 'DM / leads', 'New series'],
    pipelineGroups: [
      {
        key: 'idea',
        title: 'Offer',
        text: 'Shape the audience, promise, pain and angles that can be tested quickly.',
        steps: [0, 1],
      },
      {
        key: 'video',
        title: 'Series',
        text: 'Assemble videos with avatar, voice, captions and publishing handoff.',
        steps: [2, 3, 4],
      },
      {
        key: 'reaction',
        title: 'Signal',
        text: 'Compare retention, DMs and leads, then keep the angles worth scaling.',
        steps: [5, 6, 7],
      },
    ],
    pipelineConnectorLabels: ['batch ready', 'series published'],
    pipelineReturn: 'Signals → new series',
    pipelineReturnText: 'Retention, DMs, clicks, leads and saves become the brief for the next release.',
    pipelineSignals: ['retention', 'DMs', 'clicks', 'leads'],
    channelsTitle: 'Not a generator. A release line.',
    channelsText:
      'A real series usually means ChatGPT, avatar tools, voice, editing and autoposting. OpenShorts puts the whole flow in one line: offer, hooks, videos, publishing, signals.',
    features: [
      { icon: Sparkles, title: 'Script batch', text: 'Multiple hooks and scripts for one offer, so testing is not random.' },
      { icon: UserRound, title: 'AI avatar', text: 'UGC-style delivery through an AI character or uploaded likeness.' },
      { icon: Repeat2, title: 'Voice and lip-sync', text: 'Voiceover, lip-sync and delivery variants without manual assembly.' },
      { icon: Subtitles, title: 'Captions', text: 'Readable captions and hook overlays for the first seconds.' },
      { icon: Send, title: 'Autoposting', text: 'Publishing queue for TikTok, Instagram Reels and YouTube Shorts.' },
      { icon: KeyRound, title: 'Unit economics', text: 'Start on subscription or connect your own APIs to control cost.' },
    ],
    access: {
      title: 'Product access plus cost control',
      text:
        'The subscription gives you the release workspace. If production volume grows, bring your own keys and see where generation budget goes.',
      leftTitle: 'Start on subscription',
      leftPoints: ['no five-tool infrastructure setup', 'briefs, scripts, videos and queue in one place', 'a clear path from offer to first batch'],
      rightTitle: 'Your APIs',
      rightPoints: ['Gemini for offer analysis and scripts', 'fal.ai for video, avatars and lip-sync', 'ElevenLabs for voice', 'Upload-Post for publishing'],
    },
    faq: [
      {
        question: 'Why is a series better than one video?',
        answer:
          'One video can miss the pain, hook or delivery. A 7-10 video batch shows which angles get attention and deserve another round.',
      },
      {
        question: 'Can it create Russian videos?',
        answer:
          'Yes. Scripts, voices, captions and delivery can be created in Russian when the selected models and voices support it.',
      },
      {
        question: 'Why connect my own APIs if I have a subscription?',
        answer:
          'Subscription gives you the workspace and workflow. Your own APIs matter when you publish at volume and want direct cost control by provider.',
      },
      {
        question: 'Who is it for?',
        answer:
          'Experts, small businesses, agencies and projects that need to test offers, products, lead magnets or consultations through short videos.',
      },
      {
        question: 'How much manual work remains?',
        answer:
          'You still define the niche, offer and constraints, then approve the best variants. The handoff between scripts, avatar, voice, captions and publishing moves into the pipeline.',
      },
    ],
    finalCta: {
      title: 'Launch the first series, not just one clip',
      text: 'Start with one offer and 7-10 short videos. Compare response, then keep only the angles that show signal.',
      button: 'Build a test series',
    },
  },
};

const getInitialLanguage = () => {
  if (typeof navigator === 'undefined') return 'ru';
  return navigator.language?.toLowerCase().startsWith('en') ? 'en' : 'ru';
};

const THEME_KEY = 'openshorts_landing_theme_v2';
const THEME_LIGHT_CLASS = 'theme-light';
const THEME_DARK_CLASS = 'theme-dark';

const getInitialTheme = () => {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  return 'dark';
};

const scrollToSection = (event, sectionId) => {
  event.preventDefault();
  const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: prefersReducedMotion ? 'auto' : 'smooth',
    block: 'start',
  });
  window.history.replaceState(null, '', `#${sectionId}`);
};

const SectionHeading = ({ eyebrow, title, text }) => (
  <div className="mb-10 max-w-3xl">
    {eyebrow && <p className="mb-3 text-sm font-semibold text-cyan-300">{eyebrow}</p>}
    <h2 className="text-balance text-3xl font-bold text-white md:text-4xl">{title}</h2>
    {text && <p className="text-pretty mt-4 text-base leading-7 text-zinc-400">{text}</p>}
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
    <div className={`inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm ${tones[tone]}`}>
      <Icon size={17} />
      <span>{label}</span>
    </div>
  );
};

const ProductCard = ({ icon: Icon, title, text, points }) => (
  <article className="landing-product-card flex h-full flex-col rounded-xl border border-white/10 bg-zinc-950/55 p-6 backdrop-blur">
    <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg bg-white/10">
      <Icon size={22} className="text-cyan-200" />
    </div>
    <h3 className="text-xl font-bold text-white">{title}</h3>
    <p className="text-pretty mt-3 text-sm leading-6 text-zinc-400">{text}</p>
    <ul className="mt-auto space-y-2 pt-5">
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
      <p className="text-pretty mt-1 text-sm leading-6 text-zinc-400">{text}</p>
    </div>
  </div>
);

const LeadMagnetSection = ({ copy, onLaunchApp }) => {
  const lead = copy.leadMagnet;

  return (
    <section id="lead-magnet" className="scroll-mt-24 px-5 py-14 md:py-20">
      <div className="lead-magnet-panel mx-auto grid max-w-7xl gap-8 rounded-2xl border border-white/10 bg-zinc-950/70 p-5 md:grid-cols-[1fr_0.9fr] md:p-8 lg:p-10">
        <div>
          <div className="mb-4 inline-flex items-center gap-2 rounded-lg border border-lime-300/20 bg-lime-300/10 px-3 py-2 text-sm font-semibold text-lime-100">
            <Sparkles size={16} />
            {lead.eyebrow}
          </div>
          <h2 className="text-balance text-3xl font-bold text-white md:text-5xl">{lead.title}</h2>
          <p className="text-pretty mt-5 max-w-2xl text-base leading-7 text-zinc-300">{lead.text}</p>
          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            {lead.items.map((item) => (
              <div key={item} className="flex gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-4 text-sm leading-6 text-zinc-300">
                <Check size={16} className="mt-1 shrink-0 text-lime-200" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>

        <form
          className="lead-form-card flex flex-col justify-between rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            onLaunchApp();
          }}
        >
          <div>
            <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-300 text-zinc-950">
              <FileVideo size={22} />
            </div>
            <label htmlFor="lead-email" className="text-sm font-semibold text-cyan-100">
              {lead.inputLabel}
            </label>
            <input
              id="lead-email"
              type="email"
              placeholder={lead.placeholder}
              className="mt-3 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none transition placeholder:text-zinc-500 focus:border-cyan-200"
            />
          </div>
          <div className="mt-6">
            <button
              type="submit"
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-lime-300 px-5 py-3 font-semibold text-zinc-950 transition hover:bg-lime-200"
            >
              {lead.button}
              <ArrowRight size={18} />
            </button>
            <p className="mt-4 text-pretty text-xs leading-5 text-cyan-100/70">{lead.note}</p>
          </div>
        </form>
      </div>
    </section>
  );
};

const FAQItem = ({ id, question, answer, isOpen, onClick }) => (
  <div className="rounded-xl border border-white/10 bg-zinc-950/45">
    <button
      type="button"
      onClick={onClick}
      aria-expanded={isOpen}
      aria-controls={`${id}-panel`}
      className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-white"
    >
      <span className="font-medium">{question}</span>
      <ChevronDown size={18} className={`shrink-0 text-zinc-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
    </button>
    <p id={`${id}-panel`} hidden={!isOpen} className="px-5 pb-5 text-sm leading-6 text-zinc-400">
      {answer}
    </p>
  </div>
);

function HeroFactoryMockup({ copy, className = '' }) {
  const mockup = copy.heroMockup;
  const hooks = mockup.hooks || [mockup.script];
  const signals = mockup.signals || [mockup.analytics, mockup.leads, mockup.hypothesis];

  return (
    <aside className={`hero-factory-mockup relative mx-auto w-full max-w-xl lg:ml-auto ${className}`} aria-label={mockup.lineLabel}>
      <div className="factory-halo absolute -inset-8 -z-10 rounded-[2rem]" />
      <div className="landing-mockup-shell factory-console rounded-2xl border border-white/10 bg-zinc-950/70 p-4 shadow-[0_10px_48px_rgba(0,0,0,0.28)] backdrop-blur-xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-cyan-200">{mockup.lineLabel}</p>
            <p className="mt-1 text-lg font-bold text-white">{mockup.campaign}</p>
          </div>
          <div className="factory-live-badge rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1 text-xs font-semibold text-emerald-200">
            {mockup.status}
          </div>
        </div>

        <div className="factory-flow-strip mb-3" aria-hidden="true">
          {[mockup.idea, mockup.script, mockup.queue, mockup.hypothesis].map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>

        <div className="grid gap-3 md:grid-cols-[0.92fr_1.08fr]">
          <div className="space-y-3">
            <div className="factory-step-card rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-300/10 text-cyan-200">
                  <Sparkles size={18} />
                </div>
                <span className="text-xs text-zinc-500">01</span>
              </div>
              <p className="font-semibold text-white">{mockup.idea}</p>
              <p className="mt-1 text-sm text-zinc-400">{mockup.script}</p>
              <div className="mt-4 space-y-2">
                {hooks.map((hook, index) => (
                  <div key={hook} className="factory-hook-row flex items-start gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs leading-5 text-zinc-300">
                    <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-200" />
                    <span>{String(index + 1).padStart(2, '0')} / {hook}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="factory-step-card rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-pink-300/10 text-pink-100">
                  <UserRound size={18} />
                </div>
                <span className="text-xs text-zinc-500">02</span>
              </div>
              <p className="font-semibold text-white">{mockup.avatar}</p>
              <div className="factory-progress-track mt-4 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="factory-progress-bar h-full rounded-full bg-gradient-to-r from-cyan-300 via-fuchsia-300 to-amber-200" />
              </div>
            </div>
          </div>

          <div className="factory-video-panel rounded-xl border border-white/10 bg-white/[0.035] p-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500">{mockup.output}</p>
                <p className="font-semibold text-white">{mockup.queue}</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-200/10 text-amber-100">
                <Play size={18} />
              </div>
            </div>

            <div className="rounded-xl bg-black/35 p-3">
              <div className="factory-video-card mx-auto aspect-[9/16] max-h-52 rounded-xl border border-white/10 bg-gradient-to-br from-zinc-800 via-zinc-950 to-cyan-950 p-3">
                <div className="mb-3 h-2 w-16 rounded-full bg-white/30" />
                <div className="mt-16 space-y-2">
                  <div className="h-2 w-24 rounded-full bg-white/45" />
                  <div className="h-2 w-16 rounded-full bg-white/25" />
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
              {[
                { icon: TikTokIcon, label: 'TikTok' },
                { icon: Instagram, label: 'Reels' },
                { icon: Youtube, label: 'Shorts' },
              ].map((channel) => (
                <div key={channel.label} className="factory-channel-card rounded-lg border border-white/10 bg-white/[0.035] p-2 text-center text-zinc-300">
                  <channel.icon size={15} className="mx-auto mb-1 text-cyan-200" />
                  {channel.label}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {[
            { icon: BarChart3, value: signals[0], label: mockup.analytics },
            { icon: Send, value: signals[1], label: mockup.leads },
            { icon: Repeat2, value: signals[2], label: mockup.hypothesis },
          ].map((item) => (
            <div key={item.label} className="factory-signal-card rounded-xl border border-white/10 bg-white/[0.035] p-3">
              <div className="mb-3 flex items-center justify-between">
                <item.icon size={17} className="text-cyan-200" />
                <span className="text-xs font-semibold text-cyan-100">{item.value}</span>
              </div>
              <p className="text-sm font-semibold text-white">{item.label}</p>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

const PipelineDiagram = ({ copy }) => {
  const stageIcons = [Sparkles, Play, BarChart3];
  const connectorLabels = copy.pipelineConnectorLabels || [];

  return (
    <div className="pipeline-diagram content-loop-map rounded-2xl border border-white/10 bg-zinc-950/55 p-4 backdrop-blur md:p-6">
      <div className="content-loop-main">
        {copy.pipelineGroups.map((group, groupIndex) => {
          const Icon = stageIcons[groupIndex] || Repeat2;
          return (
            <React.Fragment key={group.key}>
              <article className={`content-loop-card pipeline-group pipeline-group-${group.key} rounded-xl border border-white/10 bg-black/25 p-5`}>
                <div className="mb-7 flex items-start justify-between gap-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-cyan-300/10 text-cyan-100">
                    <Icon size={20} />
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.035] px-2.5 py-1 text-xs font-semibold text-zinc-500">
                    {String(groupIndex + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="text-2xl font-bold text-white">{group.title}</h3>
                <p className="text-pretty mt-3 min-h-14 text-sm leading-6 text-zinc-400">{group.text}</p>
                <div className="mt-6 flex flex-wrap gap-2">
                  {group.steps.map((stepIndex) => (
                    <span key={copy.pipeline[stepIndex]} className="pipeline-node-pill rounded-full border border-white/10 bg-white/[0.045] px-3 py-1.5 text-xs font-semibold text-zinc-300">
                      {copy.pipeline[stepIndex]}
                    </span>
                  ))}
                </div>
              </article>
              {groupIndex < copy.pipelineGroups.length - 1 && (
                <div className="content-loop-connector" aria-hidden="true">
                  <span>{connectorLabels[groupIndex]}</span>
                  <ArrowRight size={18} />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      <div className="content-loop-return-lane mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-cyan-300/15 text-cyan-100">
              <Repeat2 size={18} />
            </span>
            <div>
              <p className="font-semibold text-cyan-50">{copy.pipelineReturn}</p>
              <p className="mt-1 text-sm leading-6 text-cyan-100/75">{copy.pipelineReturnText}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {copy.pipelineSignals.map((signal) => (
              <span key={signal} className="rounded-full border border-cyan-200/20 bg-black/20 px-3 py-1.5 text-xs font-semibold text-cyan-50">
                {signal}
              </span>
            ))}
          </div>
        </div>
        <div className="content-loop-return-line" aria-hidden="true">
          <span />
        </div>
      </div>
    </div>
  );
};

export default function Landing({ onLaunchApp }) {
  const [language, setLanguage] = React.useState(getInitialLanguage);
  const [openFaq, setOpenFaq] = React.useState(0);
  const [theme, setTheme] = React.useState(getInitialTheme);
  const copy = LANDING_COPY[language] || LANDING_COPY.ru;
  const isLight = theme === 'light';

  React.useEffect(() => {
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  return (
    <div className={`landing-page ${isLight ? THEME_LIGHT_CLASS : THEME_DARK_CLASS} min-h-screen overflow-hidden text-white`}>
      <div className="pointer-events-none fixed inset-0 -z-10 aurora-mesh" />

      <nav className="landing-nav fixed inset-x-0 top-0 z-50 border-b border-white/10 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <a href="#" className="flex min-h-11 items-center gap-3">
            <img src={BRAND_ICON} alt="" className="h-8 w-8 rounded-lg" />
            <span className="whitespace-nowrap text-sm font-bold sm:text-base">{BRAND_NAME}</span>
          </a>
          <div className="hidden items-center gap-5 text-sm text-zinc-400 md:flex">
            <a href="#product" className="inline-flex min-h-11 min-w-11 items-center justify-center py-2 hover:text-white">{copy.nav.product}</a>
            <a href="#pipeline" onClick={(event) => scrollToSection(event, 'pipeline')} className="inline-flex min-h-11 min-w-11 items-center justify-center py-2 hover:text-white">{copy.nav.pipeline}</a>
            <a href="#access" className="inline-flex min-h-11 min-w-11 items-center justify-center py-2 hover:text-white">{copy.nav.pricing}</a>
            <a href="#faq" className="inline-flex min-h-11 min-w-11 items-center justify-center py-2 hover:text-white">{copy.nav.faq}</a>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTheme(isLight ? 'dark' : 'light')}
              className="theme-toggle inline-flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-300 transition hover:text-white"
              aria-label={
                language === 'ru'
                  ? isLight ? 'Включить темную тему' : 'Включить светлую тему'
                  : isLight ? 'Switch to dark theme' : 'Switch to light theme'
              }
              title={
                language === 'ru'
                  ? isLight ? 'Темная тема' : 'Светлая тема'
                  : isLight ? 'Dark theme' : 'Light theme'
              }
            >
              {isLight ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <div className="hidden rounded-lg border border-white/10 bg-white/5 p-1 sm:flex">
              {['ru', 'en'].map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => setLanguage(lang)}
                  className={`flex h-11 min-w-11 items-center justify-center rounded-md px-2.5 text-xs font-semibold transition ${
                    language === lang ? 'bg-white text-zinc-950' : 'text-zinc-400 hover:text-white'
                  }`}
                  aria-pressed={language === lang}
                >
                  {lang.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onLaunchApp}
              className="min-h-11 whitespace-nowrap rounded-lg bg-white px-3 py-2 text-xs font-semibold text-zinc-950 transition hover:-translate-y-0.5 hover:bg-cyan-100 sm:px-4 sm:text-sm"
            >
              {copy.nav.login}
            </button>
          </div>
        </div>
      </nav>

      <header className="landing-hero relative px-5 pb-20 pt-32 md:pb-24 lg:min-h-[100dvh] lg:pt-36">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_50%_0%,rgba(0,128,255,0.22),transparent_34%),linear-gradient(180deg,rgba(7,8,13,0.05),#07080d_88%)]" />
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
          <div className="max-w-4xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-lg border border-lime-300/25 bg-lime-300/10 px-3 py-2 text-sm font-semibold text-lime-100">
              <Sparkles size={16} />
              <span>{copy.hero.eyebrow}</span>
            </div>
            <h1 className="text-balance max-w-5xl text-4xl font-bold text-white md:text-6xl lg:text-7xl">
              {copy.hero.title}
            </h1>
            <p className="hero-description text-pretty mt-7 max-w-3xl text-lg leading-8 text-zinc-300 md:text-xl">
              {copy.hero.description}
            </p>
            <div className="hero-billboard mt-7 grid max-w-2xl grid-cols-[0.86fr_1fr] overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
              <div className="border-r border-white/10 p-5">
                <p className="text-sm font-semibold text-lime-100">{language === 'ru' ? 'Один запуск' : 'One run'}</p>
                <div className="mt-2 flex items-end gap-2">
                  <span className="tabular-nums text-6xl font-bold leading-none text-white md:text-7xl">10</span>
                  <span className="pb-2 text-sm font-semibold text-zinc-400">{language === 'ru' ? 'роликов' : 'videos'}</span>
                </div>
              </div>
              <div className="grid grid-rows-2">
                <div className="border-b border-white/10 p-4">
                  <p className="text-xs font-semibold text-zinc-500">{language === 'ru' ? 'Вход' : 'Input'}</p>
                  <p className="mt-1 font-semibold text-white">{language === 'ru' ? 'оффер или URL' : 'offer or URL'}</p>
                </div>
                <div className="p-4">
                  <p className="text-xs font-semibold text-zinc-500">{language === 'ru' ? 'Выход' : 'Output'}</p>
                  <p className="mt-1 font-semibold text-white">Reels / Shorts / TikTok</p>
                </div>
              </div>
            </div>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={onLaunchApp}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-lime-300 px-6 py-3.5 font-semibold text-zinc-950 transition hover:bg-lime-200"
              >
                {copy.hero.primary}
                <ArrowRight size={19} />
              </button>
              <a
                href="#lead-magnet"
                onClick={(event) => scrollToSection(event, 'lead-magnet')}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-6 py-3.5 font-semibold text-white transition hover:bg-white/10"
              >
                <FileVideo size={18} />
                {copy.hero.secondary}
              </a>
            </div>
            <p className="text-pretty mt-5 max-w-3xl text-sm leading-6 text-zinc-500">{copy.hero.note}</p>
          </div>

          <HeroFactoryMockup copy={copy} className="lg:col-start-2 lg:row-span-2 lg:row-start-1" />

          <div className="lg:col-start-1">
            <div className="mt-10 flex flex-wrap gap-3">
              {copy.capabilities.map((item, index) => (
                <ServiceBadge
                  key={item.label}
                  icon={item.icon}
                  label={item.label}
                  tone={['cyan', 'pink', 'amber', 'blue'][index % 4]}
                />
              ))}
            </div>

            <div className="mt-6 grid max-w-4xl grid-cols-3 gap-2 sm:mt-10 sm:gap-3">
              {copy.proofPoints.map((point) => (
                <div key={point.title} className="hero-proof-card rounded-xl border border-white/10 bg-white/[0.045] p-3 backdrop-blur sm:p-4">
                  <p className="text-sm font-bold text-white">{point.title}</p>
                  <p className="mt-2 text-sm leading-5 text-zinc-400">{point.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main>
        <LeadMagnetSection copy={copy} onLaunchApp={onLaunchApp} />

        <section id="product" className="scroll-mt-24 px-5 py-20 md:pt-28">
          <div className="mx-auto max-w-7xl">
            <SectionHeading title={copy.channelsTitle} text={copy.channelsText} />
            <div className="grid gap-5 md:grid-cols-3">
              {copy.productCards.map((card) => (
                <ProductCard key={card.title} {...card} />
              ))}
            </div>
          </div>
        </section>

        <section id="pipeline" className="scroll-mt-24 px-5 py-20">
          <div className="mx-auto max-w-7xl">
            <SectionHeading title={copy.pipelineTitle} text={copy.pipelineText} />
            <PipelineDiagram copy={copy} />
          </div>
        </section>

        <section className="px-5 py-20">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
            <div>
              <SectionHeading
                eyebrow={language === 'ru' ? 'Рабочий процесс' : 'Workflow'}
                title={language === 'ru' ? 'Одна линия вместо ChatGPT, аватаров, голоса, монтажки и автопостинга' : 'One release line instead of scripts, avatars, voice, editing and autoposting tabs'}
                text={
                  language === 'ru'
                    ? 'Вы работаете не с набором чужих интерфейсов, а с этапами выпуска: оффер, hooks, ролики, публикация, сигналы и следующая серия.'
                    : 'Work with release stages, not vendor tabs: offer, hooks, videos, publishing, signals and the next batch.'
                }
              />
              <div className="workflow-ledger mt-6 rounded-xl border border-white/10 bg-zinc-950/55 p-4">
                {(language === 'ru'
                  ? [
                      ['01', 'Гипотеза', 'задаем нишу, оффер, аудиторию и ограничения для серии'],
                      ['02', 'Выпуск', 'собираем ролики из сценариев, аватара, голоса и субтитров'],
                      ['03', 'Повтор', 'берем реакцию аудитории и запускаем следующую связку'],
                    ]
                  : [
                      ['01', 'Hypothesis', 'set the niche, offer, audience and constraints'],
                      ['02', 'Release', 'build videos from scripts, avatar, voice and captions'],
                      ['03', 'Repeat', 'turn audience response into the next angle'],
                    ]).map(([number, title, text]) => (
                  <div key={number} className="workflow-ledger-row">
                    <span>{number}</span>
                    <strong>{title}</strong>
                    <p>{text}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {copy.features.map((feature) => (
                <FeatureRow key={feature.title} {...feature} />
              ))}
            </div>
          </div>
        </section>

        <section id="access" className="scroll-mt-24 px-5 py-20">
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
                  {language === 'ru' ? 'Цикл тестов' : 'Testing loop'}
                </div>
                <h2 className="text-3xl font-bold text-white md:text-4xl">
                  {language === 'ru' ? 'Ролики должны приносить сигналы, а не просто лежать в галерее' : 'Videos should create signals, not just sit in a gallery'}
                </h2>
                <p className="mt-4 text-base leading-7 text-zinc-400">
                  {language === 'ru'
                    ? 'Смысл OpenShorts в том, чтобы темы, hooks, аватары, CTA и форматы уточнялись по реакции аудитории. Вы не спорите о вкусах, а смотрите, что дало удержание, DM или заявку.'
                    : 'OpenShorts keeps topics, hooks, avatars, CTAs and formats improving from audience response. Instead of debating taste, you look for retention, DMs and leads.'}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { icon: Play, label: language === 'ru' ? 'серия' : 'series' },
                  { icon: BarChart3, label: language === 'ru' ? 'сигналы' : 'signals' },
                  { icon: Sparkles, label: language === 'ru' ? 'следующая связка' : 'next angle' },
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

        <section id="faq" className="scroll-mt-24 px-5 py-20">
          <div className="mx-auto max-w-3xl">
            <SectionHeading title={copy.nav.faq} text={language === 'ru' ? 'Коротко о запуске серии, API и каналах.' : 'Short answers on batches, APIs and channels.'} />
            <div className="space-y-3">
              {copy.faq.map((faq, index) => (
                <FAQItem
                  id={`landing-faq-${index}`}
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
            <h2 className="text-3xl font-bold text-white md:text-5xl">{copy.finalCta.title}</h2>
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
          <div className="flex min-h-11 items-center gap-3">
            <img src={BRAND_ICON} alt="" className="h-6 w-6 rounded-md" />
            <span>{BRAND_NAME}</span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <a href="#product" className="inline-flex min-h-11 min-w-11 items-center py-2 hover:text-white">{copy.nav.product}</a>
            <a href="#pipeline" onClick={(event) => scrollToSection(event, 'pipeline')} className="inline-flex min-h-11 min-w-11 items-center py-2 hover:text-white">{copy.nav.pipeline}</a>
            <a href="#access" className="inline-flex min-h-11 min-w-11 items-center py-2 hover:text-white">{copy.nav.pricing}</a>
            <a href="#legal" className="inline-flex min-h-11 min-w-11 items-center py-2 hover:text-white">{copy.nav.legal}</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
