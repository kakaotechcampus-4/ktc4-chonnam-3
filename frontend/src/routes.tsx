import { Routes, Route, Navigate } from 'react-router-dom';

import Login from '@/features/auth/Login';
import Home from '@/features/home/Home';
import MyPage from '@/features/mypage/MyPage';
import JobInput from '@/features/analysis/JobInput';
import Analyzing from '@/features/analysis/Analyzing';
import AnalysisFailed from '@/features/analysis/AnalysisFailed';
import RepoSelect from '@/features/analysis/RepoSelect';
import InterviewPrepare from '@/features/interview/InterviewPrepare';
import InterviewScreen from '@/features/interview/InterviewScreen';
import Report from '@/features/report/Report';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/home" element={<Home />} />
      <Route path="/mypage" element={<MyPage />} />
      <Route path="/interview/new" element={<JobInput />} />
      <Route path="/interview/analyzing/:runId" element={<Analyzing />} />
      <Route path="/interview/failed/:runId" element={<AnalysisFailed />} />
      <Route path="/interview/repos/:runId" element={<RepoSelect />} />
      <Route path="/interview/:id/prepare" element={<InterviewPrepare />} />
      <Route path="/interview/:id/session" element={<InterviewScreen />} />
      <Route path="/interview/:id/report" element={<Report />} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
