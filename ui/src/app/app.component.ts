import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder } from '@angular/forms';
import { MatButtonToggleChange } from '@angular/material/button-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable, Subject, Subscription, timer } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { HttpStatusService } from './http-status.service';

import { ChargeMode, PhaseMode, PvControl, PvControlService } from './pv-control.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, OnDestroy {
  private unsubscribe: Subject<void> = new Subject();

  ChargeMode = ChargeMode;
  PhaseMode = PhaseMode;

  busy$ = this.httpStatusService.busy();
  autoRefreshControl = this.fb.control(false);
  refreshTimer$ = timer(0, 30000).pipe(takeUntil(this.unsubscribe));
  refreshTimerSubscription: Subscription|null = null;

  pvControl: PvControl = {
    meter: {
      power_pv: 0,
      power_consumption: 0,
      power_grid: 0,
    },
    wallbox: {
      allow_charging: false,
      max_current: 0,
      phases_in: 3,
      phases_out: 0,
      power: 0,
    },
    controller: {
      mode: ChargeMode.OFF,
      desired_mode: ChargeMode.OFF,
      phase_mode: PhaseMode.AUTO,
    },
    car: {
      soc: 0,
      cruising_range: 0
    }
  };
  chargeModeControl = this.fb.control(ChargeMode.OFF);
  phaseModeControl = this.fb.control(PhaseMode.AUTO);

  constructor(
    private fb: FormBuilder, private snackBar: MatSnackBar,
    private httpStatusService: HttpStatusService, private pvControlService: PvControlService) { }

  ngOnInit(): void {
    this.httpStatusService.httpError().pipe(takeUntil(this.unsubscribe)).subscribe(errmsg => {
      console.log(`httpError: ${errmsg}`);
      this.snackBar.open(errmsg, 'Dismiss', {
        duration: 10000
      });
    });
    this.refresh();
    this.autoRefreshControl.valueChanges.subscribe(autoRefresh => {
      if (autoRefresh) {
        this.refreshTimerSubscription = this.refreshTimer$.subscribe(_ => this.refresh());
      } else {
        this.refreshTimerSubscription?.unsubscribe();
      }
    });
  }

  ngOnDestroy(): void {
    this.unsubscribe.next();
    this.unsubscribe.complete();
  }

  refresh(): void {
    this.pvControlService.getPvControl().subscribe(pv => {
      this.pvControl = pv;
      // map desired_mode==MANUAL to current mode -> show real status if e.g. somebody changes current via app/WB
      let mode = pv.controller.desired_mode;
      if (mode === ChargeMode.MANUAL) {
        mode = pv.controller.mode;
      }
      this.chargeModeControl.setValue(mode);
      this.phaseModeControl.setValue(pv.controller.phase_mode);
    },
      () => { }
    );
  }

  onChargeModeChange(event: MatButtonToggleChange): void {
    const desiredMode = event.value;
    this.pvControlService.putPvControlDesiredChargeMode(desiredMode).subscribe(
      () => {},
      () => {}
    );
  }

  onPhaseModeChange(event: MatButtonToggleChange): void {
    const mode = event.value;
    this.pvControlService.putPvControlPhaseMode(mode).subscribe(
      () => {},
      () => {}
    );
  }
}
