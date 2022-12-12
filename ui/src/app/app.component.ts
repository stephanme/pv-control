import { Component, HostListener, Inject, OnDestroy, OnInit } from '@angular/core';
import { ReactiveFormsModule, FormBuilder } from '@angular/forms';
import { Subject, Subscription, timer } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatButtonToggleChange } from '@angular/material/button-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';

import { HttpStatusService } from './http-status.service';
import { ChargeMode, PhaseMode, PvControl, PvControlService } from './pv-control.service';
import { AsyncPipe, DecimalPipe, DOCUMENT, NgIf } from '@angular/common';

@Component({
  standalone: true,
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  imports: [
    // from CommonModule
    AsyncPipe,
    DecimalPipe,
    NgIf,
    // other modules not yet available standalone
    ReactiveFormsModule,
    MatToolbarModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatButtonToggleModule,
  ]
})
export class AppComponent implements OnInit, OnDestroy {
  private unsubscribe: Subject<void> = new Subject();

  ChargeMode = ChargeMode;
  PhaseMode = PhaseMode;

  busy$ = this.httpStatusService.busy();
  autoRefreshControl = this.fb.control(false);
  refreshTimer$ = timer(0, 30000).pipe(takeUntil(this.unsubscribe));
  refreshTimerSubscription: Subscription | null = null;

  pvControl: PvControl = {
    meter: {
      error: 0,
      power_pv: 0,
      power_consumption: 0,
      power_grid: 0,
    },
    wallbox: {
      error: 0,
      allow_charging: false,
      max_current: 0,
      phases_in: 3,
      phases_out: 0,
      power: 0,
      temperature: 0,
    },
    controller: {
      error: 0,
      mode: ChargeMode.OFF,
      desired_mode: ChargeMode.OFF,
      phase_mode: PhaseMode.AUTO,
    },
    car: {
      error: 0,
      soc: 0,
      cruising_range: 0
    }
  };
  isCharging = false;
  chargingStateIcon = 'power_off';

  chargeModeControl = this.fb.control(ChargeMode.OFF);
  phaseModeControl = this.fb.control(PhaseMode.AUTO);

  static isCharging(pv: PvControl): boolean {
    return pv.wallbox.phases_out > 0;
  }

  static chargingStateIcon(pv: PvControl): string {
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
          return 'battery_50';
        }
      default: // unknown
        return 'battery_unknown';
    }
  }

  constructor(
    private fb: FormBuilder, private snackBar: MatSnackBar,
    private httpStatusService: HttpStatusService, private pvControlService: PvControlService,
    @Inject(DOCUMENT) private document: Document) { }

  ngOnInit(): void {
    this.httpStatusService.httpError().pipe(takeUntil(this.unsubscribe)).subscribe(errmsg => {
      console.log(`httpError: ${errmsg}`);
      this.snackBar.open(errmsg, 'Dismiss', {
        duration: 10000
      });
    });
    this.autoRefreshControl.valueChanges.subscribe(enable => { this.autoRefresh(enable ?? false); });
    this.refresh();
  }

  ngOnDestroy(): void {
    this.unsubscribe.next();
    this.unsubscribe.complete();
  }

  // page gets visible: (auto)refresh
  // page gets hidden: disable autorefresh 
  @HostListener('document:visibilitychange')
  onVisibilityChange() {
    if (!this.document.hidden) {
      if (this.autoRefreshControl.value) {
        // enabling autoRefresh refreshes immediately
        this.autoRefresh(true);
      } else {
        this.refresh();
      }
    } else {
      if (this.autoRefreshControl.value) {
        this.autoRefresh(false);
      }
    }
  }

  errorMeter(): boolean {
    return this.pvControl.meter.error > 3;
  }

  colorPv(): string {
    return this.errorMeter() ? 'col-grey' : 'col-yellow';
  }

  colorGrid(): string {
    if (this.errorMeter()) {
      return 'col-grey';
    } else {
      return (this.pvControl.meter.power_grid <= 0) ? 'col-green' : 'col-red';
    }
  }

  colorHome(): string {
    return this.errorMeter() ? 'col-grey' : 'col-primary';
  }

  errorCar(): boolean {
    return this.pvControl.car.error > 3;
  }
  colorCar(): string {
    return this.errorCar() ? 'col-grey' : 'col-primary';
  }

  errorWallbox(): boolean {
    return this.pvControl.wallbox.error > 3;
  }
  colorWallbox(): string {
    return this.errorWallbox() ? 'col-grey' : 'col-primary';
  }

  refresh(): void {
    this.pvControlService.getPvControl().subscribe({
      next: pv => {
        this.pvControl = pv;
        this.isCharging = AppComponent.isCharging(pv);
        this.chargingStateIcon = AppComponent.chargingStateIcon(pv);
        // map desired_mode==MANUAL to current mode -> show real status if e.g. somebody changes current via app/WB
        let mode = pv.controller.desired_mode;
        if (mode === ChargeMode.MANUAL) {
          mode = pv.controller.mode;
        }
        this.chargeModeControl.setValue(mode);
        this.phaseModeControl.setValue(pv.controller.phase_mode);
      },
      error: () => { }
    });
  }

  private autoRefresh(enable: boolean) {
    if (enable) {
      this.refreshTimerSubscription = this.refreshTimer$.subscribe(_ => this.refresh());
    } else {
      this.refreshTimerSubscription?.unsubscribe();
    }
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
}
