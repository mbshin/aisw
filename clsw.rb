# Homebrew formula template. release.sh fills in @VERSION@ and @SHA256@ and writes it to the tap
# github.com/mbshin/homebrew-tools (Formula/clsw.rb).
class Clsw < Formula
  desc "Keep Claude Code going on your next account when one hits its usage limit"
  homepage "https://github.com/mbshin/clsw"
  url "https://github.com/mbshin/clsw/archive/refs/tags/v@VERSION@.tar.gz"
  sha256 "@SHA256@"
  license "MIT"

  depends_on "fzf" # clsw resume
  depends_on "jq"
  depends_on "uv" # runs ui.py; Textual is fetched into uv's cache on the first `clsw ui`

  def install
    libexec.install "clsw", "common.sh", "on-limit.sh", "statusline.sh", "signin-browser.sh", "ui.py", "admin.sh"
    # An exec script, not a symlink, so `dirname "$0"` in clsw still finds common.sh.
    bin.write_exec_script libexec/"clsw"
  end

  def caveats
    <<~EOS
      Set up the account folders, status line and limit hook, then log in:
        clsw setup
        clsw login
      Optional, to keep typing `claude`:
        echo 'alias claude=clsw' >> ~/.zshrc
    EOS
  end

  test do
    assert_match "A: free", shell_output("#{bin}/clsw status")
  end
end
