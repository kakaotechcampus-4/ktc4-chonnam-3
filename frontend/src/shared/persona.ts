import domainLead from '@/assets/persona-domain-lead.png';
import hrManager from '@/assets/persona-hr-manager.png';
import techLead from '@/assets/persona-tech-lead.png';
import type { Persona } from '@/types/api';

/** 면접관 표시 이름. 면접 진행 화면과 리포트가 같은 라벨을 쓴다. */
export const PERSONA_LABELS: Record<Persona, string> = {
  tech_lead: '개발팀',
  hr_manager: '인사팀',
  domain_lead: '기획팀',
};

/** 아바타 원 안에 넣는 짧은 표기. */
export const PERSONA_INITIALS: Record<Persona, string> = {
  tech_lead: '개발',
  hr_manager: '인사',
  domain_lead: '기획',
};

/** 면접관 아바타. 표시 크기 80px의 2배인 160px로 넣었다. */
export const PERSONA_IMAGES: Record<Persona, string> = {
  tech_lead: techLead,
  hr_manager: hrManager,
  domain_lead: domainLead,
};

/** 화면에 세워 두는 순서. 질문이 오기 전에도 세 명을 모두 보여준다. */
export const PERSONA_ORDER: Persona[] = ['tech_lead', 'domain_lead', 'hr_manager'];
