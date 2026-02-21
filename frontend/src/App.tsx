import { clsx, type ClassValue } from 'clsx'
import { Briefcase, LayoutGrid, LogOut, Search, Settings, User } from 'lucide-react'
import { type ComponentType, type ReactNode } from 'react'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { twMerge } from 'tailwind-merge'
import JobDetails from './components/jobs/JobDetails'
import ApplicationsPage from './pages/ApplicationsPage'
import JobsPage from './pages/JobsPage'
import ProfilePage from './pages/ProfilePage'

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const SidebarItem = ({ to, icon: Icon, label, active }: { to: string; icon: ComponentType<{ className?: string }>; label: string; active?: boolean }) => (
  <Link
    to={to}
    className={cn(
      "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group",
      active
        ? "bg-white/10 text-white shadow-lg shadow-white/5"
        : "text-slate-400 hover:text-white hover:bg-white/5"
    )}
  >
    <Icon className={cn("w-5 h-5", active ? "text-white" : "group-hover:text-white")} />
    <span className="font-medium">{label}</span>
  </Link>
)

const Layout = ({ children }: { children: ReactNode }) => {
  const location = useLocation()
  const isJobBoardRoute =
    location.pathname === '/' || location.pathname.startsWith('/jobs')

  return (
    <div className="flex h-screen bg-[#0B1120] text-slate-200 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-white/5 bg-[#0D1525] flex flex-col">
        <div className="p-6">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center">
              <Briefcase className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">Career Scout</h1>
          </div>

          <nav className="space-y-2">
            <SidebarItem
              to="/jobs"
              icon={LayoutGrid}
              label="Job Board"
              active={isJobBoardRoute}
            />
            <SidebarItem
              to="/applications"
              icon={Briefcase}
              label="Applications"
              active={location.pathname === '/applications'}
            />
            <SidebarItem
              to="/profile"
              icon={User}
              label="My Profile"
              active={location.pathname === '/profile'}
            />
          </nav>
        </div>

        <div className="mt-auto p-6 border-t border-white/5">
          <nav className="space-y-2">
            <SidebarItem to="/settings" icon={Settings} label="Settings" />
            <button className="flex items-center gap-3 px-4 py-3 w-full text-slate-400 hover:text-red-400 hover:bg-red-400/5 rounded-lg transition-all">
              <LogOut className="w-5 h-5" />
              <span className="font-medium">Logout</span>
            </button>
          </nav>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-white/5 bg-[#0D1525]/50 backdrop-blur-md flex items-center justify-between px-8">
          <div className="relative w-96">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search jobs, companies, skills..."
              className="w-full bg-white/5 border border-white/10 rounded-full py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
            />
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right mr-2">
              <p className="text-sm font-medium text-white">Alex Johnson</p>
              <p className="text-xs text-slate-500">Software Engineer</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
              <User className="w-6 h-6 text-indigo-400" />
            </div>
          </div>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-8">
          {children}
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<JobsPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:id" element={<JobDetails />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
      </Routes>
    </Layout>
  )
}

export default App
