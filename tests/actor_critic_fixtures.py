from studio_editor import compose_script

CRITIQUE=dict(hook_velocity=[],visual_pacing=[],no_fluff=[],direct_response_strength=[],safety_issues=[])
HOOKS=[dict(kind='problem',text='If drain hair makes you gag, watch this.'),
       dict(kind='curiosity',text='Here is where loose shower hair can land.'),
       dict(kind='contrarian',text='A hair catcher still needs a proper cleanup.')]
BODY=('[B-ROLL: Wet hair clump on drain] [B-ROLL: Place silicone insert over drain] '
      'This reusable silicone insert sits over the drain and catches loose hair. '
      '[B-ROLL: Lift catcher and peel off collected hair] When you are done, lift it up and peel the hair off. '
      'Give it a rinse and use it again. [TEXT ON SCREEN: Rinse and reuse] Grab one before your next shower.')
EDIT=dict(script_body=BODY,hooks=HOOKS)
SCRIPT=compose_script(HOOKS[0]['text'],BODY)
