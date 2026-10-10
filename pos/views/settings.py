from django.contrib import messages
from django.shortcuts import render, redirect
from pos.forms import SettingForm
from pos.models import Setting
from pos.permissions import role_required


@role_required("Admin", "Manager")
def settings_view(request):
    setting = Setting.objects.first()
    if not setting:
        setting = Setting.objects.create()

    if request.method == "POST":
        form = SettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, "Restaurant settings updated successfully.")
            return redirect("settings")
        else:
            messages.error(request, "Failed to update settings. Please check errors.")
    else:
        form = SettingForm(instance=setting)

    return render(
        request,
        "pos/manage/settings.html",
        {
            "form": form,
            "setting": setting,
        },
    )
