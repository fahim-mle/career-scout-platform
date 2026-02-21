
const ProfilePage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-white">My Profile</h2>
        <p className="text-slate-400 mt-1">Manage your professional information and preferences.</p>
      </div>

      <div className="glass-card p-8">
        <div className="flex items-start gap-8">
          <div className="w-32 h-32 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <span className="text-4xl">AJ</span>
          </div>
          <div className="flex-1 space-y-4">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Full Name</p>
                <p className="text-lg font-medium text-white">Alex Johnson</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Title</p>
                <p className="text-lg font-medium text-white">Software Engineer</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Email</p>
                <p className="text-lg font-medium text-white">alex.j@example.com</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Location</p>
                <p className="text-lg font-medium text-white">Brisbane, Australia</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProfilePage
