import { Component, HostListener, Inject, OnDestroy, OnInit, signal, effect, computed, ChangeDetectionStrategy } from '@angular/core';
import { ReactiveFormsModule, FormBuilder } from '@angular/forms';
import { Subscription, timer } from 'rxjs';

import { MatToolbar } from '@angular/material/toolbar';
import { MatCard, MatCardContent, MatCardHeader, MatCardTitle } from '@angular/material/card';
import { MatIcon } from '@angular/material/icon';
import { MatIconButton } from '@angular/material/button';
import { MatButtonToggle, MatButtonToggleGroup } from '@angular/material/button-toggle';
import { MatButtonToggleChange } from '@angular/material/button-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';

import { HttpStatusService } from './http-status.service';
import { ChargeMode, PhaseMode, Priority, PvControl, PvControlService } from './pv-control.service';
import { DecimalPipe, DOCUMENT } from '@angular/common';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  imports: [
    // from CommonModule
    DecimalPipe,
    // material components
    MatCard,
    MatCardContent,
    MatCardHeader,
    MatCardTitle,
    MatIcon,
    MatIconButton,
    MatButtonToggle,
    MatButtonToggleGroup,
    MatToolbar,
    // other modules not yet available standalone
    ReactiveFormsModule,
  ]
})
export class AppComponent implements OnInit, OnDestroy {
  ChargeMode = ChargeMode;
  PhaseMode = PhaseMode;
  Priority = Priority;

  busy = this.httpStatusService.busy;
  // refresh every 30s, initial delay 200ms to make refresh visible and avoid network issues
  static readonly REFRESH_DELAY = 30000;
  refreshTimer$ = timer(200, AppComponent.REFRESH_DELAY);
  refreshTimerSubscription: Subscription | null = null;

  // pv card
  meterError = signal(false);
  pvIconColor = computed(() => this.meterError() ? 'col-grey' : 'col-yellow');
  pvPower = signal(0);

  // grid data
  gridPower = signal(0);
  gridIconColor = computed(() => {
    if (this.meterError()) {
      return 'col-grey';
    } else {
      return (this.gridPower() <= 0) ? 'col-green' : 'col-red';
    }
  });

  // home card
  powerConsumption = signal(0);
  homePower = computed(() => this.powerConsumption() - this.wallboxPower());
  homeIconColor = computed(() => this.meterError() ? 'col-grey' : 'col-primary');

  // battery card
  batteryPower = signal(0);
  batteryIcon = signal('battery_unknown');
  batteryIconColor = computed(() => this.meterError() ? 'col-grey' : 'col-primary');

  // car card
  carError = signal(false);
  carIconColor = computed(() => this.carError() ? 'col-grey' : 'col-primary');
  carSOC = signal(0);

  // charge mode card
  // wallbox
  wallboxError = signal(false);
  wallboxIconColor = computed(() => this.wallboxError() ? 'col-grey' : 'col-primary');
  wallboxCharging = computed(() => this.wallboxPhasesOut() > 0);
  wallboxPhasesOut = signal(0);
  wallboxMaxCurrent = signal(0);
  wallboxPower = signal(0);
  wallboxChargingIcon = signal('power_off');
  wallboxChargingIconColor = computed(() => this.wallboxError() ? 'col-grey' : 'col-primary');
  // charge mode
  chargeMode = signal(ChargeMode.OFF);
  chargeModeControl = this.fb.control(ChargeMode.OFF);
  // phase mode
  wallboxPhasesIn = signal(1);
  phaseModeControl = this.fb.control({ value: PhaseMode.DISABLED, disabled: true });
  // priority
  priority = signal(Priority.AUTO);
  priorityControl = this.fb.control(Priority.AUTO);

  // temp card
  wallboxTemperature = signal(0);

  constructor(
    private fb: FormBuilder, private snackBar: MatSnackBar,
    private httpStatusService: HttpStatusService, private pvControlService: PvControlService,
    @Inject(DOCUMENT) private document: Document) {
    effect(() => {
      const err = this.httpStatusService.httpError();
      if (err) {
        this.snackBar.open(err.errmsg, 'Dismiss', {
          duration: 10000
        });
      }
    });
  }

  ngOnInit(): void {
    this.startAutoRefresh();
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
  }

  // page gets visible: (auto)refresh
  // page gets hidden: disable autorefresh 
  @HostListener('document:visibilitychange')
  onVisibilityChange() {
    if (!this.document.hidden) {
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  startAutoRefresh() {
    if (!this.refreshTimerSubscription) {
      this.refreshTimerSubscription = this.refreshTimer$.subscribe(() => this.refresh());
    }
  }

  stopAutoRefresh() {
    this.refreshTimerSubscription?.unsubscribe();
    this.refreshTimerSubscription = null;
  }

  refresh(): void {
    this.pvControlService.getPvControl().subscribe({
      next: pv => {
        this.meterError.set(pv.meter.error > 3);
        this.pvPower.set(pv.meter.power_pv);
        this.gridPower.set(pv.meter.power_grid);
        this.powerConsumption.set(pv.meter.power_consumption);
        this.batteryPower.set(pv.meter.power_battery);
        this.batteryIcon.set(AppComponent.batteryIcon(pv));

        this.wallboxError.set(pv.wallbox.error > 3);
        this.wallboxPower.set(pv.wallbox.power);
        this.wallboxPhasesIn.set(pv.wallbox.phases_in);
        this.wallboxPhasesOut.set(pv.wallbox.phases_out);
        this.wallboxMaxCurrent.set(pv.wallbox.max_current);
        this.wallboxTemperature.set(pv.wallbox.temperature);

        this.carError.set(pv.car.error > 3);
        this.carSOC.set(pv.car.soc);

        this.chargeMode.set(pv.controller.mode);
        this.wallboxChargingIcon.set(AppComponent.wallboxChargingIcon(pv));

        // map desired_mode==MANUAL to current mode -> show real status if e.g. somebody changes current via app/WB
        let mode = pv.controller.desired_mode;
        if (mode === ChargeMode.MANUAL) {
          mode = pv.controller.mode;
        }
        this.chargeModeControl.setValue(mode);
        this.phaseModeControl.setValue(pv.controller.phase_mode);
        if (pv.controller.phase_mode === PhaseMode.DISABLED) {
          this.phaseModeControl.disable()
        } else {
          this.phaseModeControl.enable()
        }

        this.priority.set(pv.controller.priority);
        this.priorityControl.setValue(pv.controller.desired_priority);
      },
      error: () => { }
    });
  }

  onChargeModeChange(event: MatButtonToggleChange): void {
    const desiredMode = event.value;
    this.pvControlService.putPvControlDesiredChargeMode(desiredMode).subscribe({
      next: () => { },
      error: () => { }
    });
  }

  onPhaseModeChange(event: MatButtonToggleChange): void {
    const mode = event.value;
    this.pvControlService.putPvControlPhaseMode(mode).subscribe({
      next: () => { },
      error: () => { }
    });
  }

  onPriorityChange(event: MatButtonToggleChange): void {
    const prio = event.value;
    this.pvControlService.putPvControlPriority(prio).subscribe({
      next: () => { },
      error: () => { }
    });
  }

  static wallboxChargingIcon(pv: PvControl): string {
    switch (pv.wallbox.car_status) {
      case 1: // NoVehicle
        return 'power_off';
      case 2: // Charging
        return 'battery_charging_50';
      case 3: // WaitingForVehicle
        return 'hourglass_bottom';
      case 4: // ChargingFinished
        // TODO: SOC (allow_charging=on but not charging -> car rejected charging)
        if (pv.wallbox.allow_charging) {
          return 'battery_full';
        } else {
          return 'battery_3_bar';
        }
      default: // unknown
        return 'battery_unknown';
    }
  }

  static battery_discharging_icons = ["battery_0_bar", "battery_1_bar", "battery_2_bar", "battery_3_bar", "battery_4_bar", "battery_5_bar", "battery_6_bar", "battery_full"];
  static battery_charging_icons = ["battery_charging_20", "battery_charging_20", "battery_charging_30", "battery_charging_50", "battery_charging_60", "battery_charging_80", "battery_charging_90", "battery_charging_full"];
  static batteryIcon(pv: PvControl): string {
    if (pv.meter.error > 3) {
      return 'battery_unknown';
    }
    // 0..6 bars and full
    const bars = Math.round(pv.meter.soc_battery / (100.0 / 7));
    if (pv.meter.power_battery < 0) {
      return AppComponent.battery_charging_icons[bars];
    } else {
      return AppComponent.battery_discharging_icons[bars];
    }
  }
}
